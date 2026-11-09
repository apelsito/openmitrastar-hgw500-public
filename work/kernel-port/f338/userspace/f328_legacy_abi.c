/* No module_init, Linux headers, MMIO, threads, delayed work, allocation or IO. */
#include "f328_legacy_abi.h"
extern void f338_oem_timer_call(uint32_t function,uint32_t argument);
uint32_t f328_abi_jiffies, f328_fault;
static uint32_t clock_hz, log_calls;
static unsigned char active[2];
uint32_t f328_ticks_from_ns(uint32_t high,uint32_t low)
{
    uint32_t rem=0,quotient=0;
    unsigned i;
    for(i=64;i;i--) {
        uint32_t bit=i>32?(high>>(i-33))&1u:(low>>(i-1))&1u;
        rem=(rem<<1)|bit;quotient<<=1;
        if(rem>=5000000u) {rem-=5000000u;quotient|=1;}
    }
    return quotient;
}

static int timer_index(struct f328_timer_legacy *t)
{
    if ((void *)t==(void *)(f328_oem_bss+0x92f8)) return 0;
    if ((void *)t==(void *)(f328_oem_bss+0x9314)) return 1;
    f328_fault=1; return -1;
}
void *f328_abi_memcpy(void *d,const void *s,size_t n)
{
    unsigned char *to=d; const unsigned char *from=s; size_t i;
    for (i=0;i<n;i++) to[i]=from[i];
    return d;
}
void *f328_abi_memset(void *d,int value,size_t n)
{
    unsigned char *to=d; size_t i;
    for (i=0;i<n;i++) to[i]=(unsigned char)value;
    return d;
}
static uint32_t divide(uint32_t a,uint32_t b,uint32_t *rem)
{
    uint32_t q=0,r=0; unsigned n;
    if (!b) { f328_fault=2; *rem=0; return 0; }
    for (n=32;n;n--) {
        uint32_t carry=r>>31;
        r=(r<<1)|((a>>(n-1))&1u);
        if (carry || r>=b) { r-=b; q|=1u<<(n-1); }
    }
    *rem=r; return q;
}
uint32_t f328_abi___udivsi3(uint32_t a,uint32_t b) { uint32_t r; return divide(a,b,&r); }
uint32_t f328_abi___umodsi3(uint32_t a,uint32_t b) { uint32_t r; (void)divide(a,b,&r); return r; }
int f328_abi_printk(const char *format,...) { (void)format; log_calls++; return 0; }
void *f328_abi_radar_ocac_info_addr_get(void) { return f328_oem_bss+0x9104; }
void f328_abi_init_timer_key(struct f328_timer_legacy *t,const char *name,void *key)
{
    int i=timer_index(t); (void)name; (void)key;
    if (i<0) return;
    f328_abi_memset(t,0,sizeof(*t)); t->slack=-1; active[i]=0;
}
int f328_abi_mod_timer(struct f328_timer_legacy *t,uint32_t expires)
{
    int i=timer_index(t), old;
    uint32_t expected=(uint32_t)(uintptr_t)(f328_oem_text+(i?0xb824:0xb638)-0x8e8c);
    if (i<0) return 0;
    if (t->function!=expected || t->data!=0) { f328_fault=3; return 0; }
    old=active[i]; t->expires=expires; active[i]=1;
    t->next=(uint32_t)(uintptr_t)t; t->prev=t->next;
    return old;
}
int f328_abi_del_timer(struct f328_timer_legacy *t)
{
    int i=timer_index(t), old;
    if (i<0) return 0;
    old=active[i]; active[i]=0; t->next=0; return old;
}
int f328_virtual_clock(uint32_t hz,uint32_t now)
{
    if (!hz || hz>1000000u || active[0] || active[1]) return -1;
    clock_hz=hz; f328_abi_jiffies=now; return 0;
}
void f328_abi_do_gettimeofday(struct f328_timeval32 *tv)
{
    uint32_t r=0, remainder=0, unit;
    if (!clock_hz) { f328_fault=4; tv->sec=0;tv->usec=0;return; }
    tv->sec=(int32_t)divide(f328_abi_jiffies,clock_hz,&r);
    /* Caller may use only audited HZ values dividing one million. */
    unit=divide(1000000u,clock_hz,&remainder);
    if (remainder) { f328_fault=5;tv->usec=0;return; }
    tv->usec=(int32_t)(r*unit);
}
int f328_advance(uint32_t now)
{
    unsigned calls;
    if (!clock_hz || f328_fault || (int32_t)(now-f328_abi_jiffies)<0) return -1;
    for (calls=0;calls<8;calls++) {
        int pick=-1,i; uint32_t when=now, fn, expected;
        struct f328_timer_legacy *t;
        for (i=0;i<2;i++) {
            struct f328_timer_legacy *t=(void *)(f328_oem_bss+(i?0x9314:0x92f8));
            if (active[i] && (int32_t)(now-t->expires)>=0) {
                uint32_t due=(int32_t)(t->expires-f328_abi_jiffies)<0?f328_abi_jiffies:t->expires;
                if (pick<0 || (int32_t)(due-when)<0) { pick=i;when=due; }
            }
        }
        if (pick<0) { f328_abi_jiffies=now;return f328_fault?-1:0; }
        t=(void *)(f328_oem_bss+(pick?0x9314:0x92f8));
        fn=t->function;
        expected=(uint32_t)(uintptr_t)(f328_oem_text+(pick?0xb824:0xb638)-0x8e8c);
        if (fn!=expected || t->data) { f328_fault=3;return -1; }
        active[pick]=0; t->next=0; f328_abi_jiffies=when;
#ifdef F328_ABI_TEST
        f328_test_dispatch(fn,t->data);
#else
        f338_oem_timer_call(fn,t->data);
#endif
        if (f328_fault) return -1;
    }
    f328_fault=6; return -1;
}
