#include "Touch.h"
#include "Screen.h"
#include <atomic>
#include <math.h>
#include <string.h>
#ifndef ZX_TOUCH_BUILD_COMMIT
#define ZX_TOUCH_BUILD_COMMIT "local-unknown"
#endif

static dispatch_queue_t touchQueue;
static dispatch_source_t watchdog;
static IOHIDEventSystemClientRef transmitClient;
// Scheduled and retained for the lifetime of SpringBoard on its MAIN run loop.
// No cross-thread unschedule or detached polling thread.
static IOHIDEventSystemClientRef monitorClient;
static ZXTouchState state;
static NSMutableSet<NSNumber *> *sessions;
static uint64_t nextSession = 2, senderID, txFrames, rejects, resetFrames;
static uint64_t sentTimestamps[256];
static unsigned timestampCursor;
static double screenWidth, screenHeight;
static uint64_t timeoutMs = 30000;
static unsigned indexBase;
static BOOL verbose;
static std::atomic_bool observationPending(false);

static uint64_t nowMs(void) {
    return (uint64_t)([NSProcessInfo processInfo].systemUptime * 1000.0);
}

// Shared log budget limits HID/TX/error logging even if an input source floods.
static void touchLog(NSString *message) {
    static uint64_t window;
    static unsigned lines, dropped;
    uint64_t second = nowMs() / 1000;
    if (window != second) {
        if (dropped) NSLog(@"ZXTouchTouch: suppressed=%u", dropped);
        window = second; lines = 0; dropped = 0;
    }
    if (lines++ < 20) NSLog(@"ZXTouchTouch: %@", message);
    else ++dropped;
}

// Must be called on touchQueue. DispatchEvent returns void; success here means
// submitted to IOKit, NEVER confirmed delivered to a target application's view.
static BOOL submitFrame(const ZXTouchFrame *frame) {
    if (!frame->count || !frame->mask) return YES;
    if (!senderID || !transmitClient || screenWidth <= 0 || screenHeight <= 0) {
        touchLog(@"TX refused: live sender/client/screen not ready; state unchanged");
        return NO;
    }
    uint64_t timestamp = mach_absolute_time();
    Boolean active = frame->active_count > 0;
    uint32_t parentMask = frame->mask;
    if (parentMask & kIOHIDDigitizerEventTouch) parentMask |= kIOHIDDigitizerEventIdentity;
    IOHIDEventRef parent = IOHIDEventCreateDigitizerEvent(kCFAllocatorDefault,
        timestamp, kIOHIDDigitizerTransducerTypeHand, 99, 1, parentMask, 0,
        0, 0, 0, 0, 0, active, active, 0);
    if (!parent) return NO;
    IOHIDEventSetIntegerValue(parent, kIOHIDEventFieldDigitizerIsDisplayIntegrated, 1);
    IOHIDEventSetIntegerValue(parent, kIOHIDEventFieldIsBuiltIn, 1);
    for (size_t i = 0; i < frame->count; ++i) {
        const ZXTouchContact *contact = &frame->contacts[i];
        IOHIDEventRef child = IOHIDEventCreateDigitizerFingerEvent(kCFAllocatorDefault,
            timestamp, indexBase + contact->slot, indexBase + contact->identity,
            contact->mask, contact->x10 / (10.0 * screenWidth),
            contact->y10 / (10.0 * screenHeight), 0, 0, 0,
            contact->touching, contact->touching, 0);
        if (!child) { CFRelease(parent); return NO; }
        IOHIDEventSetFloatValue(child, kIOHIDEventFieldDigitizerMajorRadius, 0.04);
        IOHIDEventSetFloatValue(child, kIOHIDEventFieldDigitizerMinorRadius, 0.04);
        IOHIDEventAppendEvent(parent, child, 0);
        CFRelease(child);
    }
    // Append can modify collection fields. Set the final aggregate explicitly.
    IOHIDEventSetIntegerValue(parent, kIOHIDEventFieldDigitizerEventMask, parentMask);
    IOHIDEventSetIntegerValue(parent, kIOHIDEventFieldDigitizerRange, active);
    IOHIDEventSetIntegerValue(parent, kIOHIDEventFieldDigitizerTouch, active);
    IOHIDEventSetSenderID(parent, senderID);
    sentTimestamps[timestampCursor++ % 256] = timestamp;
    IOHIDEventSystemClientDispatchEvent(transmitClient, parent);
    ++txFrames;
    if (verbose) {
        NSMutableString *details = [NSMutableString string];
        for (size_t i = 0; i < frame->count; ++i) {
            const ZXTouchContact *c = &frame->contacts[i];
            [details appendFormat:@" slot=%u/index=%u/id=%u/mask=%x/touch=%d",
                c->slot, indexBase+c->slot, indexBase+c->identity, c->mask, c->touching];
        }
        touchLog([NSString stringWithFormat:@"TX seq=%llu time=%llu sender=%llx active=%zu mask=%x%@ (submission only)",
            txFrames, timestamp, senderID, frame->active_count, parentMask, details]);
    }
    CFRelease(parent);
    return YES;
}

static void releaseOwner(uint64_t owner, NSString *reason) {
    ZXTouchState next; ZXTouchFrame frame;
    zx_touch_release(&state, owner, &next, &frame);
    if (!frame.mask) return;
    if (submitFrame(&frame)) {
        state = next; ++resetFrames;
        touchLog([NSString stringWithFormat:@"release owner=%llu reason=%@ remaining=%zu", owner, reason, frame.active_count]);
    }
    // A failed release retains state for retry by the watchdog; do not pretend
    // the OS released it. SIGKILL/SpringBoard crash cannot run cleanup code.
}

static void initializeQueue(void) {
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        touchQueue = dispatch_queue_create("com.zjx.zxtouch.touch-state", DISPATCH_QUEUE_SERIAL);
        sessions = [NSMutableSet setWithObject:@1];
        NSDictionary *config = [NSDictionary dictionaryWithContentsOfFile:
            @"/var/mobile/Library/ZXTouch/config/tweak/touch-diagnostics.plist"];
        verbose = [config[@"enabled"] boolValue];
        NSInteger base = [config[@"indexBase"] integerValue];
        indexBase = base == 64 ? 64 : 0; // A/B only, not a guaranteed HID namespace.
        double timeout = [config[@"timeoutSeconds"] doubleValue];
        if (isfinite(timeout) && timeout >= 1 && timeout <= 300) timeoutMs = (uint64_t)(timeout * 1000);
        transmitClient = IOHIDEventSystemClientCreate(kCFAllocatorDefault);
        watchdog = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, touchQueue);
        dispatch_source_set_timer(watchdog, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), NSEC_PER_SEC, NSEC_PER_SEC/10);
        dispatch_source_set_event_handler(watchdog, ^{
            @autoreleasepool {
                ZXTouchState next; ZXTouchFrame frame;
                zx_touch_expire(&state, nowMs(), timeoutMs, &next, &frame);
                if (frame.mask && submitFrame(&frame)) {
                    state = next; ++resetFrames;
                    touchLog([NSString stringWithFormat:@"watchdog released inactive virtual contacts; remaining=%zu", frame.active_count]);
                }
            }
        });
        dispatch_resume(watchdog);
        dispatch_async(touchQueue, ^{
            touchLog([NSString stringWithFormat:@"initialized indexBase=%u timeoutMs=%llu verbose=%d; physical events are never replayed", indexBase, timeoutMs, verbose]);
        });
    });
}

uint64_t zxTouchOpenSession(void) {
    initializeQueue();
    __block uint64_t owner;
    dispatch_sync(touchQueue, ^{ owner = nextSession++; [sessions addObject:@(owner)]; });
    return owner;
}
void zxTouchCloseSession(uint64_t owner) {
    if (owner < 2) return;
    initializeQueue();
    dispatch_sync(touchQueue, ^{ [sessions removeObject:@(owner)]; releaseOwner(owner, @"disconnect"); });
}
void zxTouchReleaseSession(uint64_t owner) {
    initializeQueue();
    dispatch_sync(touchQueue, ^{ if ([sessions containsObject:@(owner)]) releaseOwner(owner, @"explicit"); });
}
NSString *zxTouchStatusJSON(void) {
    initializeQueue();
    __block NSString *json;
    dispatch_sync(touchQueue, ^{
        unsigned active = 0;
        for (unsigned i = 0; i < ZX_TOUCH_SLOTS; ++i) active += state.slots[i].active;
        NSDictionary *info = @{@"senderReady":@(senderID != 0 && transmitClient != NULL),
            @"activeVirtual":@(active), @"submittedFrames":@(txFrames), @"rejectedFrames":@(rejects),
            @"releaseFrames":@(resetFrames), @"indexBase":@(indexBase), @"timeoutMs":@(timeoutMs),
            @"buildCommit":@ZX_TOUCH_BUILD_COMMIT, @"appReceiptVerified":@NO};
        NSData *data = [NSJSONSerialization dataWithJSONObject:info options:0 error:nil];
        json = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    });
    return json;
}

void performTouchFromRawData(UInt8 *eventData, uint64_t owner) {
    if (!eventData) return;
    // Task's buffer is NUL-terminated by the socket parser / script caller.
    // Bound the read and copy before entering the serialized state transaction.
    size_t length = strnlen((const char *)eventData, ZX_TOUCH_MAX_PAYLOAD + 1);
    NSData *payload = [NSData dataWithBytes:eventData length:length];
    initializeQueue();
    dispatch_sync(touchQueue, ^{
        if (![sessions containsObject:@(owner)]) { ++rejects; return; }
        ZXTouchState next; ZXTouchFrame frame;
        ZXTouchResult result = zx_touch_prepare(&state, (const uint8_t *)payload.bytes,
            payload.length, owner, (uint32_t)(screenWidth*10), (uint32_t)(screenHeight*10), nowMs(), &next, &frame);
        if (result != ZXTouchOK) {
            ++rejects;
            touchLog([NSString stringWithFormat:@"reject owner=%llu reason=%s bytes=%zu", owner, zx_touch_result_string(result), length]);
            return;
        }
        if (submitFrame(&frame)) state = next;
        else ++rejects;
    });
}

static void observeDigitizer(void *target, void *refcon, IOHIDEventQueueRef queue, IOHIDEventRef event) {
    if (!event || IOHIDEventGetType(event) != kIOHIDEventTypeDigitizer) return;
    // Bounded outstanding work. This observer is diagnostic, never a physical
    // state mirror; dropped observations cannot cancel or replay hardware input.
    if (observationPending.exchange(true)) return;
    CFRetain(event);
    dispatch_async(touchQueue, ^{
        @autoreleasepool {
            uint64_t timestamp = IOHIDEventGetTimeStamp(event);
            BOOL ownEcho = NO;
            for (unsigned i = 0; i < 256; ++i)
                if (sentTimestamps[i] && sentTimestamps[i] == timestamp) { ownEcho = YES; break; }
            uint64_t observedSender = IOHIDEventGetSenderID(event);
            BOOL integrated = IOHIDEventGetIntegerValue(event, kIOHIDEventFieldDigitizerIsDisplayIntegrated) != 0;
            NSArray *children = (__bridge NSArray *)IOHIDEventGetChildren(event);
            BOOL hasFinger = NO;
            NSMutableString *details = [NSMutableString string];
            for (id item in children) {
                IOHIDEventRef child = (__bridge IOHIDEventRef)item;
                if (IOHIDEventGetType(child) != kIOHIDEventTypeDigitizer) continue;
                NSInteger type = IOHIDEventGetIntegerValue(child, kIOHIDEventFieldDigitizerType);
                if (type == kIOHIDDigitizerTransducerTypeFinger) hasFinger = YES;
                if (verbose && details.length < 1800) {
                    [details appendFormat:@" index=%ld/id=%ld/type=%ld/mask=%lx/touch=%ld/range=%ld",
                        (long)IOHIDEventGetIntegerValue(child, kIOHIDEventFieldDigitizerIndex),
                        (long)IOHIDEventGetIntegerValue(child, kIOHIDEventFieldDigitizerIdentity), (long)type,
                        (long)IOHIDEventGetIntegerValue(child, kIOHIDEventFieldDigitizerEventMask),
                        (long)IOHIDEventGetIntegerValue(child, kIOHIDEventFieldDigitizerTouch),
                        (long)IOHIDEventGetIntegerValue(child, kIOHIDEventFieldDigitizerRange)];
                }
            }
            if (!senderID && !ownEcho && integrated && hasFinger && observedSender) {
                senderID = observedSender;
                touchLog([NSString stringWithFormat:@"captured LIVE display finger sender=%llx; no cached sender used", senderID]);
                if (!verbose) {
                    // Teardown is returned to the same run loop that scheduled
                    // this client, and no observation is needed after capture.
                    dispatch_async(dispatch_get_main_queue(), ^{
                        if (monitorClient) {
                            IOHIDEventSystemClientUnregisterEventCallback(monitorClient);
                            IOHIDEventSystemClientUnscheduleWithRunLoop(monitorClient, CFRunLoopGetMain(), kCFRunLoopCommonModes);
                            CFRelease(monitorClient); monitorClient = NULL;
                        }
                    });
                }
            }
            if (verbose) touchLog([NSString stringWithFormat:@"HID time=%llu sender=%llx integrated=%d source=%@ children=%lu%@ (NOT app receipt)",
                timestamp, observedSender, integrated, ownEcho ? @"our-timestamp-echo" : @"unclassified", (unsigned long)children.count, details]);
            CFRelease(event);
            observationPending.store(false);
        }
    });
}

void initSenderId(void) {
    initializeQueue();
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        dispatch_async(dispatch_get_main_queue(), ^{
            monitorClient = IOHIDEventSystemClientCreate(kCFAllocatorDefault);
            if (!monitorClient) { NSLog(@"ZXTouchTouch: failed to create HID observer"); return; }
            IOHIDEventSystemClientRegisterEventCallback(monitorClient, observeDigitizer, NULL, NULL);
            IOHIDEventSystemClientScheduleWithRunLoop(monitorClient, CFRunLoopGetMain(), kCFRunLoopCommonModes);
        });
    });
}
void initTouchGetScreenSize(void) {
    double width = [Screen getScreenWidth], height = [Screen getScreenHeight];
    initializeQueue();
    dispatch_sync(touchQueue, ^{ screenWidth = width; screenHeight = height; });
}
