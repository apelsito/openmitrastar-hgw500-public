/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F367_AP_POLICY_H
#define F367_AP_POLICY_H
#ifdef __KERNEL__
#include <linux/types.h>
typedef u32 f367_u32;
typedef s32 f367_s32;
#else
#include <stdint.h>
#include <stdbool.h>
typedef uint32_t f367_u32;
typedef int32_t f367_s32;
#endif
/* This is admission/timer policy, not a replacement radar classifier. The
 * first operational candidate is AP channel52/20MHz, with fallback36. */
struct f367_ap_policy {
 f367_u32 boot_until,nop_until,cac_until,cac_generation;
 bool initialized,nop,cac_pending,cac_done;
};
static inline bool f367_due(f367_u32 now,f367_u32 deadline)
{return (f367_s32)(now-deadline)>=0;}
static inline void f367_policy_init(struct f367_ap_policy *p,f367_u32 now,f367_u32 hz)
{p->boot_until=now+1800u*hz;p->nop_until=p->cac_until=p->cac_generation=0;p->initialized=true;p->nop=p->cac_pending=p->cac_done=false;}
static inline bool f367_dfs_clear(const struct f367_ap_policy*p,f367_u32 now)
{return p->initialized&&f367_due(now,p->boot_until)&&(!p->nop||f367_due(now,p->nop_until));}
static inline void f367_invalidate_cac(struct f367_ap_policy*p)
{p->cac_pending=p->cac_done=false;p->cac_generation=0;}
static inline bool f367_begin_cac(struct f367_ap_policy*p,f367_u32 now,f367_u32 hz,f367_u32 generation,unsigned channel,unsigned bw)
{
 f367_invalidate_cac(p);
 if(!generation||channel!=52||bw!=20||!f367_dfs_clear(p,now))return false;
 p->cac_until=now+70u*hz;p->cac_generation=generation;p->cac_pending=true;return true;
}
static inline bool f367_finish_cac(struct f367_ap_policy*p,f367_u32 now,f367_u32 generation,unsigned channel,unsigned bw)
{
 if(!p->cac_pending||!generation||generation!=p->cac_generation||channel!=52||bw!=20||!f367_dfs_clear(p,now)||!f367_due(now,p->cac_until))return false;
 p->cac_pending=false;p->cac_done=true;return true;
}
static inline void f367_mark_radar(struct f367_ap_policy*p,f367_u32 now,f367_u32 hz)
{p->nop=true;p->nop_until=now+1800u*hz;f367_invalidate_cac(p);}
static inline bool f367_tx_allowed(const struct f367_ap_policy*p,f367_u32 now,f367_u32 generation,unsigned channel,unsigned bw,bool ap,bool detector,bool radar)
{
 if(!p->initialized||!ap)return false;
 if(channel==36)return true;
 return channel==52&&bw==20&&detector&&!radar&&f367_dfs_clear(p,now)&&p->cac_done&&generation&&generation==p->cac_generation&&f367_due(now,p->cac_until);
}
#endif
