#include "TouchState.h"
#include <string.h>

static uint32_t decimal(const uint8_t *p, size_t n) {
    uint32_t value = 0;
    for (size_t i = 0; i < n; ++i) value = value * 10 + (uint32_t)(p[i] - '0');
    return value;
}

static void make_frame(const ZXTouchState *before, const ZXTouchState *after,
                       const uint32_t masks[ZX_TOUCH_SLOTS], ZXTouchFrame *frame) {
    memset(frame, 0, sizeof(*frame));
    for (unsigned i = 0; i < ZX_TOUCH_SLOTS; ++i) {
        const ZXTouchSlot *slot = &after->slots[i];
        frame->active_count += slot->active ? 1 : 0;
        if (!slot->active && !before->slots[i].active) continue;
        ZXTouchContact *contact = &frame->contacts[frame->count++];
        contact->slot = i;
        contact->identity = i + 1; // stable and distinct for all virtual contacts
        contact->mask = masks[i];
        contact->x10 = slot->x10;
        contact->y10 = slot->y10;
        contact->touching = slot->active;
        frame->mask |= masks[i];
    }
}

ZXTouchResult zx_touch_prepare(const ZXTouchState *state, const uint8_t *bytes,
    size_t length, uint64_t owner, uint32_t width10, uint32_t height10,
    uint64_t now_ms, ZXTouchState *next, ZXTouchFrame *frame) {
    if (!state || !bytes || !next || !frame || !owner || !width10 || !height10 ||
        !length || bytes[0] < '1' || bytes[0] > '9') return ZXTouchBadFormat;
    size_t count = (size_t)(bytes[0] - '0');
    if (length != 1 + count * ZX_TOUCH_RECORD_BYTES) return ZXTouchBadFormat;
    for (size_t i = 0; i < length; ++i)
        if (bytes[i] < '0' || bytes[i] > '9') return ZXTouchBadFormat;
    ZXTouchState candidate = *state;
    bool seen[ZX_TOUCH_SLOTS] = {false};
    uint32_t masks[ZX_TOUCH_SLOTS] = {0};
    for (size_t i = 0; i < count; ++i) {
        const uint8_t *record = bytes + 1 + i * ZX_TOUCH_RECORD_BYTES;
        unsigned phase = decimal(record, 1), index = decimal(record + 1, 2);
        uint32_t x = decimal(record + 3, 5), y = decimal(record + 8, 5);
        if (index >= ZX_TOUCH_SLOTS) return ZXTouchBadSlot;
        if (seen[index]) return ZXTouchDuplicateSlot;
        seen[index] = true;
        if (phase > ZX_TOUCH_MOVE) return ZXTouchBadFormat;
        if (x > width10 || y > height10) return ZXTouchBadCoordinate;
        ZXTouchSlot *slot = &candidate.slots[index];
        if (slot->active && slot->owner != owner) return ZXTouchWrongOwner;
        if ((phase == ZX_TOUCH_DOWN) == slot->active) return ZXTouchBadTransition;
        slot->active = phase != ZX_TOUCH_UP;
        slot->owner = owner;
        slot->x10 = x; slot->y10 = y;
        masks[index] = phase == ZX_TOUCH_MOVE ? ZX_TOUCH_POSITION_MASK :
                      (ZX_TOUCH_RANGE_MASK | ZX_TOUCH_TOUCH_MASK);
    }
    // A valid frame is activity for the entire owner's gesture, including a
    // held stationary finger while another owned finger is being moved.
    for (unsigned i = 0; i < ZX_TOUCH_SLOTS; ++i)
        if (candidate.slots[i].active && candidate.slots[i].owner == owner)
            candidate.slots[i].last_activity_ms = now_ms;
    make_frame(state, &candidate, masks, frame);
    *next = candidate;
    return ZXTouchOK;
}

static void release_matching(const ZXTouchState *state, uint64_t owner,
    uint64_t now_ms, uint64_t timeout_ms, bool expire,
    ZXTouchState *next, ZXTouchFrame *frame) {
    *next = *state;
    uint32_t masks[ZX_TOUCH_SLOTS] = {0};
    for (unsigned i = 0; i < ZX_TOUCH_SLOTS; ++i) {
        ZXTouchSlot *slot = &next->slots[i];
        bool matches = expire ? (timeout_ms && now_ms >= slot->last_activity_ms &&
            now_ms - slot->last_activity_ms >= timeout_ms) : (!owner || owner == slot->owner);
        if (slot->active && matches) {
            slot->active = false;
            masks[i] = ZX_TOUCH_RANGE_MASK | ZX_TOUCH_TOUCH_MASK;
        }
    }
    make_frame(state, next, masks, frame);
}
void zx_touch_release(const ZXTouchState *state, uint64_t owner,
    ZXTouchState *next, ZXTouchFrame *frame) {
    release_matching(state, owner, 0, 0, false, next, frame);
}
void zx_touch_expire(const ZXTouchState *state, uint64_t now_ms,
    uint64_t timeout_ms, ZXTouchState *next, ZXTouchFrame *frame) {
    release_matching(state, 0, now_ms, timeout_ms, true, next, frame);
}
const char *zx_touch_result_string(ZXTouchResult result) {
    switch (result) {
        case ZXTouchOK: return "ok";
        case ZXTouchBadFormat: return "bad-format";
        case ZXTouchBadSlot: return "bad-slot";
        case ZXTouchDuplicateSlot: return "duplicate-slot";
        case ZXTouchBadTransition: return "bad-transition";
        case ZXTouchWrongOwner: return "slot-owned-by-another-client";
        case ZXTouchBadCoordinate: return "outside-portrait-screen";
    }
    return "unknown";
}
