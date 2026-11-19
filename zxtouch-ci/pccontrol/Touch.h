#ifndef TOUCH_H
#define TOUCH_H
#import <Foundation/Foundation.h>
#include "headers/IOHIDEvent.h"
#include "headers/IOHIDEventSystemClient.h"
#include <mach/mach_time.h>
#include "TouchState.h"
#define TOUCH_UP ZX_TOUCH_UP
#define TOUCH_DOWN ZX_TOUCH_DOWN
#define TOUCH_MOVE ZX_TOUCH_MOVE

// Session 1 is reserved for in-process legacy scripts. TCP sessions never reuse
// tokens, so work queued before a disconnect cannot resurrect released touches.
uint64_t zxTouchOpenSession(void);
void zxTouchCloseSession(uint64_t owner);
void zxTouchReleaseSession(uint64_t owner);
NSString *zxTouchStatusJSON(void);
void performTouchFromRawData(UInt8 *eventData, uint64_t owner = 1);
void initSenderId(void);
void initTouchGetScreenSize(void);
#endif
