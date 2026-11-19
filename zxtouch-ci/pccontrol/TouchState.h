#ifndef ZX_TOUCH_STATE_H
#define ZX_TOUCH_STATE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define ZX_TOUCH_SLOTS 20
#define ZX_TOUCH_RECORD_BYTES 13
#define ZX_TOUCH_MAX_PAYLOAD (1 + 9 * ZX_TOUCH_RECORD_BYTES)
#define ZX_TOUCH_UP 0
#define ZX_TOUCH_DOWN 1
#define ZX_TOUCH_MOVE 2
#define ZX_TOUCH_RANGE_MASK 1u
#define ZX_TOUCH_TOUCH_MASK 2u
#define ZX_TOUCH_POSITION_MASK 4u

typedef struct {
    bool active;
    uint64_t owner, last_activity_ms;
    uint32_t x10, y10;
} ZXTouchSlot;
typedef struct { ZXTouchSlot slots[ZX_TOUCH_SLOTS]; } ZXTouchState;
typedef struct {
    unsigned slot;
    uint32_t identity, mask, x10, y10;
    bool touching;
} ZXTouchContact;
typedef struct {
    ZXTouchContact contacts[ZX_TOUCH_SLOTS];
    size_t count, active_count;
    uint32_t mask;
} ZXTouchFrame;
typedef enum {
    ZXTouchOK, ZXTouchBadFormat, ZXTouchBadSlot, ZXTouchDuplicateSlot,
    ZXTouchBadTransition, ZXTouchWrongOwner, ZXTouchBadCoordinate
} ZXTouchResult;

// Transactional: no output state is committed by this module. Caller dispatches
// the frame successfully, then assigns *state = next. Caller must serialize.
ZXTouchResult zx_touch_prepare(const ZXTouchState *state, const uint8_t *bytes,
    size_t length, uint64_t owner, uint32_t width10, uint32_t height10,
    uint64_t now_ms, ZXTouchState *next, ZXTouchFrame *frame);
// owner=0 releases all; otherwise only the matching owner's contacts.
void zx_touch_release(const ZXTouchState *state, uint64_t owner,
    ZXTouchState *next, ZXTouchFrame *frame);
void zx_touch_expire(const ZXTouchState *state, uint64_t now_ms,
    uint64_t timeout_ms, ZXTouchState *next, ZXTouchFrame *frame);
const char *zx_touch_result_string(ZXTouchResult result);
#ifdef __cplusplus
}
#endif
#endif
