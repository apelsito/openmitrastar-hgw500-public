"""Prepare AP-only DFS policy over F366; authority and image sealing stay gated."""
from pathlib import Path
import hashlib,json,shutil
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f366';DST=ROOT/'work/kernel-port/f367'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def once(s,a,b):require(s.count(a)==1,'ambiguous anchor '+a[:90]);return s.replace(a,b,1)
def replace_fn(s,name,body):old=extract(s,name);return once(s,old,body+'\n')
POLICY=r'''/* SPDX-License-Identifier: GPL-2.0-only */
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
'''
ADAPTER=r'''/* SPDX-License-Identifier: GPL-2.0-only */
#include "f367_ap_policy.h"
static DEFINE_SPINLOCK(f367_policy_lock);
static struct f367_ap_policy f367_policy;
static bool qdrv_f367_ap(void)
{
 struct ieee80211com *ic=qdrv_radar_cb.ic;
 return ic&&ic->ic_opmode==IEEE80211_M_HOSTAP&&!ieee80211_is_repeater(ic);
}
static bool qdrv_f367_tx_allowed(void)
{
 struct ieee80211com *ic=qdrv_radar_cb.ic;struct ieee80211_channel*chan;
 unsigned long flags;u32 generation;bool result;
 if(!ic||(chan=ic->ic_curchan)==NULL||chan==IEEE80211_CHAN_ANYC)return false;
 generation=qdrv_f332_generation();
 spin_lock_irqsave(&f367_policy_lock,flags);
 result=f367_tx_allowed(&f367_policy,(u32)jiffies,generation,chan->ic_ieee,ic->ic_radar_bw,qdrv_f367_ap(),qdrv_radar_cb.enabled&&!!generation,ieee80211_is_chan_radar_detected(chan));
 spin_unlock_irqrestore(&f367_policy_lock,flags);return result;
}
static bool qdrv_f367_cac_begin(struct ieee80211_channel*chan)
{
 unsigned long flags;bool result;struct ieee80211com*ic=qdrv_radar_cb.ic;
 spin_lock_irqsave(&f367_policy_lock,flags);
 result=qdrv_f367_ap()&&f367_begin_cac(&f367_policy,(u32)jiffies,HZ,READ_ONCE(qdrv_f332.cac_generation),chan->ic_ieee,ic->ic_radar_bw);
 spin_unlock_irqrestore(&f367_policy_lock,flags);return result;
}
static bool qdrv_f367_cac_finish(struct ieee80211_channel*chan)
{
 unsigned long flags;bool result;u32 generation=qdrv_f332_generation();
 spin_lock_irqsave(&f367_policy_lock,flags);
 result=qdrv_f367_ap()&&f367_finish_cac(&f367_policy,(u32)jiffies,generation,chan->ic_ieee,qdrv_radar_cb.ic->ic_radar_bw);
 spin_unlock_irqrestore(&f367_policy_lock,flags);return result;
}
static void qdrv_f367_mark_radar(void)
{unsigned long flags;spin_lock_irqsave(&f367_policy_lock,flags);f367_mark_radar(&f367_policy,(u32)jiffies,HZ);spin_unlock_irqrestore(&f367_policy_lock,flags);}
static void qdrv_f367_init(void)
{unsigned long flags;spin_lock_irqsave(&f367_policy_lock,flags);if(!f367_policy.initialized)f367_policy_init(&f367_policy,(u32)jiffies,HZ);spin_unlock_irqrestore(&f367_policy_lock,flags);}
'''
def main():
 require(not (DST/'source-manifest.json').exists(),'immutable F367 source already sealed');DST.mkdir(parents=True,exist_ok=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(SRC/sub,DST/sub,dirs_exist_ok=True)
 for p in (DST/'kernel').iterdir():
  if p.is_file():p.write_bytes(p.read_bytes().replace(b'qtn_radar_f366',b'qtn_radar_f367').replace(b'openmitrastar_radar_f366',b'openmitrastar_radar_f367').replace(b'OMF366',b'OMF367'))
 p=DST/'kernel/f332_provider.c';s=p.read_text();s=once(s,'#define F338_RELEASE_QUALIFIED 0','#include "f367_build_gate.h"')
 s=s.replace('F338_RELEASE_QUALIFIED','F367_NATIVE_AUTHORITY_BUILD')
 s=once(s,'if(channel!=36)return -EPERM','if(channel!=36&&channel!=52)return -EPERM')
 s=s.replace('profile_channel=36','profile_channel=52')
 s=once(s,'f332_hw_dirty(),F367_NATIVE_AUTHORITY_BUILD,started','f332_hw_dirty(),0,started')
 s=once(s,'MODULE_DESCRIPTION("F341 bounded channel36 diagnostic: GPL kernel and userspace OEM engine; authority disabled");','MODULE_DESCRIPTION("F367 experimental AP52 DFS: GPL kernel, original userspace OEM engine, gated build");')
 p.write_bytes(s.encode());(DST/'kernel/f367_build_gate.h').write_text('/* Generated build copies may set this to1 only after exact F366 evidence. */\n#define F367_NATIVE_AUTHORITY_BUILD 0\n')
 qdir=DST/'qdrv/qdrv';(qdir/'f367_ap_policy.h').write_bytes(POLICY.encode());(qdir/'qdrv_f367_ap.inc').write_bytes(ADAPTER.encode())
 p=qdir/'qdrv_radar.c';s=p.read_text()
 s=once(s,'static bool qdrv_f338_enable_tx(void);','static bool qdrv_f338_enable_tx(void);\nstatic bool qdrv_f338_force_tx_off(void);\nstatic bool qdrv_f367_tx_allowed(void);')
 s=once(s,'#include "qdrv_f332_ready.inc"','#include "qdrv_f332_ready.inc"\n#include "qdrv_f367_ap.inc"')
 s=replace_fn(s,'sys_disable_xmit','static void sys_disable_xmit(void)\n{\n /* Never report stopped after an unconfirmed hostlink operation. */\n (void)qdrv_f338_force_tx_off();\n}')
 # A production profile cannot administratively erase NOP or re-enable TX.
 s=replace_fn(s,'qdrv_radar_disable','void qdrv_radar_disable(void)\n{\n if(qdrv_radar_configured)\n  pr_warn_ratelimited("OMF367DFS administrative-disable-refused preserve-nop=1 reboot-required=1\\n");\n}')
 s=replace_fn(s,'qdrv_cac_instant_completed','void qdrv_cac_instant_completed(void)\n{\n pr_warn_ratelimited("OMF367DFS instant-cac-refused\\n");\n}')
 # DFS requirement never depends on the writable DOTH/debug bypass bits.
 s=replace_fn(s,'qdrv_radar_is_rdetection_required','bool qdrv_radar_is_rdetection_required(const struct ieee80211_channel *chan)\n{\n return chan&&chan!=IEEE80211_CHAN_ANYC&&(chan->ic_flags&IEEE80211_CHAN_DFS);\n}')
 old=extract(s,'sys_enable_rdetection');new=old.replace('if (DBG_LOG_FUNC_TEST(QDRV_LF_DFS_DISALLOWRADARDETECT)) {','if (false) {');s=once(s,old,new)
 old=extract(s,'start_cac');new=once(old,'if (!qdrv_f332_begin_cac(cur_chan))','if (!qdrv_f332_begin_cac(cur_chan) || !qdrv_f367_cac_begin(cur_chan))')
 start=new.index('\tif (DBG_LOG_FUNC_TEST(QDRV_LF_DFS_QUICKTIMER)) {');end=new.index('\n\tmod_timer(cac_timer, expires);',start);new=new[:start]+new[end:];s=once(s,old,new)
 old=extract(s,'cac_completed_action');new=once(old,'if(!qdrv_f332_complete_cac(chan) || !qdrv_f338_accept_cac(chan)){','if(!qdrv_f332_complete_cac(chan) || !qdrv_f367_cac_finish(chan) || !qdrv_f338_accept_cac(chan)){');s=once(s,old,new)
 old=extract(s,'start_nonoccupy');new=once(old,'expires = jiffies + ic->ic_non_occupancy_period;','expires = jiffies + 1800 * HZ;\n\tqdrv_f367_mark_radar();')
 start=new.index('\tif (DBG_LOG_FUNC_TEST(QDRV_LF_DFS_QUICKTIMER)) {');end=new.index('\n\tmod_timer(nonoccupy_timer, expires);',start);new=new[:start]+new[end:];s=once(s,old,new)
 # The native callback owns the full event. OEM test/intercept paths cannot
 # consume it before TX-off, NOP or evacuation. Existing CSA machinery stays.
 old=extract(s,'qdrv_radar_detected');new=old
 start=new.index('\tif (qw->radar_detect_callback) {');end=new.index('\t/* set radar_found_flag',start)
 new=new[:start]+'\t/* F367 AP profile: no optional callback, MARKDFS or test bypass. */\n\tsys_disable_xmit();\n'+new[end:]
 require(new.count('\t/* stop cac if any */')==2,'radar CAC anchors changed')
 new=new.replace('\t/* stop cac if any */','\tif(!qdrv_f367_ap()){sys_disable_xmit();return;}\n\t/* stop cac if any */',1)
 s=once(s,old,new)
 # Avoid background scan/ICAC/STA selection: use only qualified non-DFS36.
 old=extract(s,'dfs_action');new='''static void dfs_action(uint8_t new_ieee, bool radar_detected_during_cac)
{
 struct ieee80211com*ic=qdrv_radar_cb.ic;struct ieee80211_channel*destination;
 (void)new_ieee;(void)radar_detected_during_cac;
 sys_disable_xmit();
 if(!qdrv_f367_ap())return;
 destination=ieee80211_find_channel_by_ieee(ic,36);
 if(!destination||(destination->ic_flags&IEEE80211_CHAN_DFS)||ieee80211_is_chan_radar_detected(destination)){
  pr_err_ratelimited("OMF367DFS evacuation-no-safe-destination tx-admission=closed\\n");return;
 }
 dfs_action_after_newchan_select(destination);
 ic->ic_chan_switch_reason_record(ic,IEEE80211_CSW_REASON_DFS);
}''';s=once(s,old,new+'\n')
 s=once(s,'\tqdrv_f332_ready_init();','\tqdrv_f332_ready_init();\n\tqdrv_f367_init();')
 p.write_bytes(s.encode())
 p=qdir/'qdrv_f338_availability.inc';s=p.read_text();s=once(s,'if (!qdrv_radar_cb.ic || qdrv_f332_ready_stopping() ||','if (!qdrv_radar_cb.ic || !qdrv_f367_tx_allowed() || qdrv_f332_ready_stopping() ||');s=once(s,'if (qdrv_f332_ready_stopping() || READ_ONCE(qdrv_f338_health.tx_fault) ||','if (!qdrv_f367_tx_allowed() || qdrv_f332_ready_stopping() || READ_ONCE(qdrv_f338_health.tx_fault) ||');p.write_bytes(s.encode())
 # Existing F338 availability fixture exercises that code independently of
 # the separately tested F367 timer gate; production has no stub definition.
 p=DST/'qdrv/tests/test_ready.c';s=p.read_text();anchor='#include "../qdrv/qdrv_f338_availability.inc"';s=once(s,anchor,'static bool qdrv_f367_tx_allowed(void){return true;}\n'+anchor);p.write_bytes(s.encode())
 pins={p.relative_to(DST).as_posix():sha(p) for p in DST.rglob('*') if p.is_file()}
 baseline={p.relative_to(SRC).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (SRC/sub).rglob('*') if p.is_file()}
 changed=sorted(n for n in set(pins)|set(baseline) if pins.get(n)!=baseline.get(n))
 report={'schema':'openmitrastar.f367-ap-dfs-source/v1','status':'PREPARED_AUTHORITY_DISABLED_PENDING_F366_PHYSICAL_PASS','source':str(DST),'source_pins':pins,'baseline_pins':baseline,'changed_files':changed,'initial_profile':{'role':'AP_ONLY','dfs_channel':52,'bandwidth':20,'fallback':36,'cac_seconds':70,'nop_seconds':1800,'boot_dfs_quarantine_seconds':1800,'ocac_enabled':False,'weather_channels_enabled':False},'classifier_preprocessor_postfilter_changed':False,'f355_lifetime_changed':False,'hardware_actions':False,'compose_seal_allowed':False}
 (DST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':str(DST),'status':report['status'],'changed_files':changed}))
if __name__=='__main__':main()
