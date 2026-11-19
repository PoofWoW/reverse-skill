#include "TouchState.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static ZXTouchResult prepare(ZXTouchState *s, const char *p, uint64_t owner,
    uint64_t now, ZXTouchState *next, ZXTouchFrame *f) {
    return zx_touch_prepare(s, (const uint8_t *)p, strlen(p), owner, 11700, 25320, now, next, f);
}
static void one(ZXTouchState *s, unsigned phase, unsigned slot, uint64_t owner,
    uint64_t now, ZXTouchFrame *f) {
    char p[32]; snprintf(p,sizeof(p),"1%u%02u%05u%05u",phase,slot,1234u,5678u);
    ZXTouchState next;
    assert(prepare(s,p,owner,now,&next,f)==ZXTouchOK); *s=next;
}
static const ZXTouchContact *find(const ZXTouchFrame *f, unsigned slot) {
    for (size_t i=0; i<f->count; ++i) if(f->contacts[i].slot==slot) return &f->contacts[i];
    abort();
}
static void lifecycle(void) {
    ZXTouchState s={0}, next; ZXTouchFrame f;
    one(&s,1,0,2,100,&f);
    assert(f.count==1 && f.active_count==1 && f.mask==3);
    assert(f.contacts[0].x10==1234 && f.contacts[0].touching);
    one(&s,1,19,2,200,&f);
    assert(f.count==2 && f.active_count==2);
    assert(find(&f,0)->mask==0); // stationary finger is NOT another down
    assert(find(&f,19)->identity!=find(&f,0)->identity);
    uint32_t identity=find(&f,0)->identity;
    one(&s,2,19,2,300,&f);
    assert(find(&f,0)->mask==0 && find(&f,19)->mask==4);
    assert(s.slots[0].last_activity_ms==300); // whole owner is alive
    one(&s,0,0,2,400,&f);
    assert(f.active_count==1 && !find(&f,0)->touching && find(&f,0)->identity==identity);
    one(&s,0,19,2,500,&f);
    assert(f.count==1 && f.active_count==0 && f.mask==3);
    zx_touch_release(&s,0,&next,&f); assert(!f.count && !f.mask);
}
static void invalid(void) {
    ZXTouchState s={0}, next; ZXTouchFrame f;
    const char *bad[]={"", "0", "2", "a", "1100000000000", "112000000000000", // slot 20
        "139000000000000", "110-0000000000", "11000000000000\r\n", "11001170099999"};
    for(size_t i=0;i<sizeof(bad)/sizeof(*bad);++i) {
        ZXTouchState before=s;
        assert(prepare(&s,bad[i],2,0,&next,&f)!=ZXTouchOK);
        assert(!memcmp(&before,&s,sizeof(s)));
    }
    assert(prepare(&s,"12000123405678",2,0,&next,&f)==ZXTouchBadTransition);
    one(&s,1,7,2,100,&f);
    assert(prepare(&s,"11070123405678",2,0,&next,&f)==ZXTouchBadTransition);
    assert(prepare(&s,"12070123405678",3,0,&next,&f)==ZXTouchWrongOwner);
    // Same slot twice in one frame: no partial down must escape validation.
    ZXTouchState empty={0};
    assert(prepare(&empty,"210701234056782070123405678",2,0,&next,&f)==ZXTouchDuplicateSlot);
    assert(!empty.slots[7].active);
    assert(prepare(&empty,"11071170105678",2,0,&next,&f)==ZXTouchBadCoordinate);
    uint8_t arbitrary[130]; memset(arbitrary, '1', sizeof(arbitrary));
    for(size_t n=0;n<=sizeof(arbitrary);++n) {
        arbitrary[0]='9';
        ZXTouchResult r=zx_touch_prepare(&empty,arbitrary,n,2,11700,25320,1,&next,&f);
        assert(r!=ZXTouchOK); // either bad length, duplicate or invalid coordinate
    }
}
static void cleanup(void) {
    ZXTouchState s={0}, next; ZXTouchFrame f;
    one(&s,1,7,2,100,&f); one(&s,1,8,3,200,&f);
    zx_touch_release(&s,2,&next,&f);
    assert(!next.slots[7].active && next.slots[8].active);
    assert(f.active_count==1 && find(&f,8)->mask==0); s=next;
    zx_touch_expire(&s,300,150,&next,&f); assert(!f.mask);
    zx_touch_expire(&s,350,150,&next,&f); assert(f.mask==3 && f.active_count==0);s=next;
    zx_touch_expire(&s,500,150,&next,&f);assert(!f.count);
    one(&s,1,8,4,600,&f);zx_touch_release(&s,3,&next,&f);
    assert(next.slots[8].active && !f.mask); // old session cannot release a new owner
    zx_touch_expire(&s,1,100,&next,&f);assert(!f.mask); // monotonic boundary
    zx_touch_release(&s,0,&next,&f);assert(f.mask && !f.active_count);
}
static void randomized(void) {
    ZXTouchState s={0}; ZXTouchFrame f;
    srand(16);
    for(unsigned n=0;n<20000;++n) {
        unsigned slot=(unsigned)rand()%ZX_TOUCH_SLOTS;
        unsigned phase=s.slots[slot].active ? ((rand()%3)==0 ? 0 : 2) : 1;
        uint64_t owner=2+slot%3;
        one(&s,phase,slot,owner,n,&f);
        size_t active=0;
        bool seen[ZX_TOUCH_SLOTS]={0};
        for(unsigned i=0;i<ZX_TOUCH_SLOTS;++i)active+=s.slots[i].active;
        assert(f.active_count==active && f.count<=ZX_TOUCH_SLOTS);
        for(size_t i=0;i<f.count;++i) {
            unsigned ix=f.contacts[i].slot;assert(!seen[ix]);seen[ix]=true;
            assert(f.contacts[i].touching==s.slots[ix].active);
            if(ix!=slot)assert(f.contacts[i].mask==0);
        }
    }
}
int main(void) { lifecycle();invalid();cleanup();randomized();puts("touch state: lifecycle, atomic validation, owner cleanup, watchdog and 20000 transitions passed"); }
