/* Private, offline-only facade for the exact OEM classifier. */
#ifndef F328_LEGACY_ABI_H
#define F328_LEGACY_ABI_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/stddef.h>
typedef u32 uint32_t;
typedef s32 int32_t;
typedef unsigned long uintptr_t;
#else
#include <stdint.h>
#include <stddef.h>
#endif
struct f328_timer_legacy {
    uint32_t next, prev, expires, base, function, data;
    int32_t slack;
};
_Static_assert(sizeof(struct f328_timer_legacy)==28,"OEM timer stride");
_Static_assert(offsetof(struct f328_timer_legacy,function)==16,"OEM callback offset");
_Static_assert(offsetof(struct f328_timer_legacy,data)==20,"OEM timer data offset");
struct f328_timeval32 { int32_t sec, usec; };
extern unsigned char f328_oem_bss[];
extern unsigned char f328_oem_text[];
extern uint32_t f328_abi_jiffies;
extern uint32_t f328_fault;
/* Sets only virtual time; no host kernel timer/workqueue is ever passed OEM. */
int f328_virtual_clock(uint32_t hz, uint32_t now);
int f328_advance(uint32_t now);
uint32_t f328_ticks_from_ns(uint32_t high,uint32_t low);
void f328_abi_init_timer_key(struct f328_timer_legacy *, const char *, void *);
int f328_abi_mod_timer(struct f328_timer_legacy *, uint32_t);
int f328_abi_del_timer(struct f328_timer_legacy *);
void f328_abi_do_gettimeofday(struct f328_timeval32 *);
void *f328_abi_radar_ocac_info_addr_get(void);
void *f328_abi_memcpy(void *, const void *, size_t);
void *f328_abi_memset(void *, int, size_t);
uint32_t f328_abi___udivsi3(uint32_t, uint32_t);
uint32_t f328_abi___umodsi3(uint32_t, uint32_t);
int f328_abi_printk(const char *, ...);
#ifdef F328_ABI_TEST
void f328_test_dispatch(uint32_t, uint32_t);
#endif
#endif
