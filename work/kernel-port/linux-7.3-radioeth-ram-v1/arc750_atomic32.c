/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* GCC ABI helpers for the single-core ARC750 without LLOCK/SCOND.
 * Linux7.3 arc_usr_cmpxchg is the same UP-only atomic primitive used by libc.
 * Alignment and mapped writable storage are the caller's atomic ABI contract.
 * SYNC gives conservative full ordering for every requested memory model.
 */
typedef unsigned int u32;
_Static_assert(sizeof(u32)==4,"GCC atomic 4-byte ABI");

#ifndef OM_ATOMIC_HOST_TEST
static inline void full_barrier(void)
{
 __asm__ volatile("sync" ::: "memory");
}
static inline u32 atomic_load32(volatile u32 *pointer)
{
 return *pointer;
}
static inline u32 cmpxchg32(volatile u32 *pointer,u32 expected,u32 desired)
{
 register long r0 __asm__("r0")=(long)pointer;
 register long r1 __asm__("r1")=expected;
 register long r2 __asm__("r2")=desired;
 register long r8 __asm__("r8")=248; /* __NR_arc_specific_syscall + 4 */
 __asm__ volatile("trap0" : "+r"(r0) : "r"(r1),"r"(r2),"r"(r8) : "memory","cc");
 return (u32)r0;
}
#endif

u32 om_fetch_and32(volatile void *,u32,int) __asm__("__atomic_fetch_and_4");
u32 om_fetch_or32(volatile void *,u32,int) __asm__("__atomic_fetch_or_4");
u32 om_exchange32(volatile void *,u32,int) __asm__("__atomic_exchange_4");

u32 om_fetch_and32(volatile void *address,u32 mask,int model)
{
 volatile u32 *pointer=address;
 u32 expected=atomic_load32(pointer),previous;
 (void)model;
 full_barrier();
 for (;;) {
  previous=cmpxchg32(pointer,expected,expected & mask);
  if(previous==expected)break;
  expected=previous;
 }
 full_barrier();
 return expected;
}

u32 om_fetch_or32(volatile void *address,u32 mask,int model)
{
 volatile u32 *pointer=address;
 u32 expected=atomic_load32(pointer),previous;
 (void)model;
 full_barrier();
 for (;;) {
  previous=cmpxchg32(pointer,expected,expected | mask);
  if(previous==expected)break;
  expected=previous;
 }
 full_barrier();
 return expected;
}

u32 om_exchange32(volatile void *address,u32 value,int model)
{
 volatile u32 *pointer=address;
 u32 expected=atomic_load32(pointer),previous;
 (void)model;
 full_barrier();
 for (;;) {
  previous=cmpxchg32(pointer,expected,value);
  if(previous==expected)break;
  expected=previous;
 }
 full_barrier();
 return expected;
}
