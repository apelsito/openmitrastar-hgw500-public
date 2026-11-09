"""Prepare an immutable AP52 regulatory-publication revision; no device I/O."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f367r4-hostlink-ack'
DST=ROOT/'work/kernel-port/f367r5-regulatory-profile'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.4-f367r5-regulatory-profile/overlay'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('source anchor '+a[:70])
 return s.replace(a,b,1)
def main():
 if DST.exists() or OVERLAY.exists():raise ValueError('immutable R5 source exists')
 DST.mkdir(parents=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(SRC/sub,DST/sub)
 # Copy the exact shared ABI declarations instead of inventing a channel layout.
 shared=ROOT/'work/sources/Quantenna-GPL/drivers/include/shared/net80211'
 ioctl=(shared/'ieee80211_ioctl.h').read_text();chan=(shared/'_ieee80211.h').read_text()
 from test_f355_lifetime import extract
 import re
 defines=[]
 for name,body in [('IEEE80211_CHAN_MAX',chan),('IEEE80211_CHAN_BYTES',chan),('IEEE80211_CHAN_DFS',chan),('IEEE80211_CHAN_PASSIVE',chan),('IEEE80211_IOCTL_GETPARAM',ioctl),('IEEE80211_IOCTL_GETCHANLIST',ioctl),('IEEE80211_IOCTL_GETCHANINFO',ioctl),('IEEE80211_IOCTL_EXT',ioctl),('SIOCDEV_SUBIO_BASE',ioctl),('SIOCDEV_SUBIO_SET_MARK_DFS_CHAN',ioctl)]:
  matches=re.findall(r'^#define\s+'+name+r'\s+[^\n]+',body,re.M)
  if len(matches)!=1:raise ValueError('ABI define '+name)
  defines+=matches
 structs=[]
 for name in ('ieee80211req_chanlist','ieee80211_chan','ieee80211req_chaninfo'):
  start=ioctl.index('struct '+name+' {');end=ioctl.index(';',ioctl.index('}',start))+1
  structs.append(ioctl[start:end])
 reg=re.search(r'IEEE80211_PARAM_REGULATORY_REGION\s*=\s*(\d+)',ioctl).group(1)
 header='/* SPDX-License-Identifier: GPL-2.0-only\n * Exact declarations extracted from the OEM shared headers; pins in source manifest. */\n#ifndef F367R5_IOCTL_H\n#define F367R5_IOCTL_H\n#define __packed __attribute__((packed))\n'+'\n'.join(defines)+'\n#define IEEE80211_PARAM_REGULATORY_REGION '+reg+'\n'+'\n'.join(structs)+'''\n_Static_assert(sizeof(int)==4,"OEM int wire size");
_Static_assert(sizeof(struct ieee80211_chan)==7,"OEM packed channel size");
_Static_assert(offsetof(struct ieee80211_chan,ic_flags)==2,"OEM channel flags offset");
_Static_assert(offsetof(struct ieee80211req_chaninfo,ic_chans)==4,"OEM table offset");
_Static_assert(sizeof(struct ieee80211req_chaninfo)==1792,"OEM table size");
#if defined(__arc__)
_Static_assert(sizeof(struct iwreq)==32,"ARC iwreq size");
_Static_assert(offsetof(struct iwreq,u.data.length)==20,"ARC iw_point length");
_Static_assert(offsetof(struct iwreq,u.data.flags)==22,"ARC iw_point flags");
#endif
#endif
'''
 (DST/'userspace').mkdir();(DST/'userspace/f367r5_oem_ioctl.h').write_bytes(header.encode())
 shutil.copyfile(ROOT/'tools/f367r5_dfs_profile.c',DST/'userspace/om-f367-dfs-profile.c')
 p=DST/'qdrv/qdrv/qdrv_f367_control.inc';s=p.read_text()
 s=once(s,' unsigned channel=0,bw=0,phymode=0,configured=', ' unsigned target_present=0,target_active=0,target_dfs=0,target_radar=0,publish_allowed=0;\n unsigned channel=0,bw=0,phymode=0,configured=')
 s=once(s,' quarantine=!policy.initialized||now<qend;', ''' if(configured&&ic){
  unsigned i;
  target_active=!!isset(ic->ic_chan_active,52);
  for(i=0;i<ic->ic_nchans;i++)if(ic->ic_channels[i].ic_ieee==52){
   target_present=1;target_dfs=!!(ic->ic_channels[i].ic_flags&IEEE80211_CHAN_DFS);
   target_radar=!!ieee80211_is_chan_radar_detected(&ic->ic_channels[i]);break;
  }
  publish_allowed=qdrv_f367_ap()&&channel==36&&bw==80&&ic->ic_country_code==CTRY_SPAIN&&
   qdrv_radar_first_call&&!qdrv_radar_cb.enabled&&!control_fault&&!READ_ONCE(qdrv_f338_health.tx_fault)&&
   !policy.nop&&!policy.cac_pending&&!policy.cac_done&&!READ_ONCE(f367_on_dfs)&&
   !READ_ONCE(f367_transition_prepared)&&!READ_ONCE(f367_switch_inflight)&&!target_radar;
 }
 quarantine=!policy.initialized||now<qend;''')
 s=once(s,'\\\"rf_silence_proven\\\":false}', '\\\"target52_present\\\":%u,\\\"target52_active\\\":%u,\\\"target52_dfs\\\":%u,\\\"target52_radar\\\":%u,\\\"profile_publish_allowed\\\":%u,\\\"rf_silence_proven\\\":false}')
 s=once(s,'READ_ONCE(f367_native_callbacks));','READ_ONCE(f367_native_callbacks),target_present,target_active,target_dfs,target_radar,publish_allowed);')
 s=once(s,'static int f367_control_set(', '''static int f367_control_reject(const char*reason,int error)
{
 pr_warn_ratelimited("OMF367_CONTROL_REJECT reason=%s error=%d\\n",reason,error);
 return error;
}
static int f367_control_set(''')
 replacements={
  'if(!READ_ONCE(qdrv_radar_configured)||!ic||!qdrv_f367_ap())return -EPERM;':'if(!READ_ONCE(qdrv_radar_configured)||!ic||!qdrv_f367_ap())return f367_control_reject("not-configured-ap",-EPERM);',
  'if(READ_ONCE(f367_control_fault)||READ_ONCE(qdrv_f338_health.tx_fault))return -EIO;':'if(READ_ONCE(f367_control_fault)||READ_ONCE(qdrv_f338_health.tx_fault))return f367_control_reject("latched-fault",-EIO);',
  'chan=READ_ONCE(ic->ic_curchan);if(!chan||chan==IEEE80211_CHAN_ANYC)return -EAGAIN;':'chan=READ_ONCE(ic->ic_curchan);if(!chan||chan==IEEE80211_CHAN_ANYC)return f367_control_reject("current-channel-invalid",-EAGAIN);',
  'if(chan->ic_ieee!=36||qdrv_radar_cb.region!=DFS_RQMT_EU||ic->ic_country_code!=CTRY_SPAIN)return -EPERM;':'if(chan->ic_ieee!=36||qdrv_radar_cb.region!=DFS_RQMT_EU||ic->ic_country_code!=CTRY_SPAIN)return f367_control_reject("prepare-not36-eu-es",-EPERM);',
  'if(!target||!(target->ic_flags&IEEE80211_CHAN_DFS)||ieee80211_is_chan_radar_detected(target))return -EBUSY;':'''if(!target)return f367_control_reject("prepare-target52-inactive-or-missing",-EBUSY);
  if(!(target->ic_flags&IEEE80211_CHAN_DFS))return f367_control_reject("prepare-target52-not-dfs",-EBUSY);
  if(ieee80211_is_chan_radar_detected(target))return f367_control_reject("prepare-target52-radar",-EBUSY);''',
  'if(!allowed)return -EBUSY;':'if(!allowed)return f367_control_reject("prepare-policy-clock-nop-or-transition",-EBUSY);',
  'if(!qdrv_f338_force_tx_off())return -EIO;':'if(!qdrv_f338_force_tx_off())return f367_control_reject("prepare-tx-off-unconfirmed",-EIO);',
  'return -EINVAL;':'return f367_control_reject("unknown-command",-EINVAL);'
 }
 for a,b in replacements.items():s=once(s,a,b)
 p.write_bytes(s.encode())
 old=ROOT/'versions/lyoko-foundation-6.11.2-f367r3-owned-lock-release/overlay'
 shutil.copytree(old,OVERLAY)
 common=OVERLAY/'usr/libexec/openmitrastar/f367-shell-common'
 text=common.read_text();text=once(text,"f367_fields='","f367_fields='target52_present target52_active target52_dfs target52_radar profile_publish_allowed ");common.write_bytes(text.encode())
 control=OVERLAY/'usr/sbin/om-f367-control';text=control.read_text()
 text=once(text,' # PREPARE rechecks the real kernel clocks/NOP and closes TX before mutation.', ''' # Read the real active bitmap and channel record before requesting PREPARE.
 "${OM_F367_PROFILE:-/usr/sbin/om-f367-dfs-profile}" check || fail target52-regulatory-readback
 # PREPARE rechecks the real kernel clocks/NOP and closes TX before mutation.''')
 control.write_bytes(text.encode())
 pins={p.relative_to(DST).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (DST/sub).rglob('*') if p.is_file()}
 previous=json.loads((SRC/'source-manifest.json').read_text())
 changed=[n for n,h in pins.items() if previous['source_pins'].get(n)!=h]
 if changed!=['qdrv/qdrv/qdrv_f367_control.inc']:raise ValueError(changed)
 authority=[shared/'ieee80211_ioctl.h',shared/'_ieee80211.h',ROOT/'work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c',SRC/'qdrv/qdrv/qdrv_wlan.c']
 report=dict(schema='openmitrastar.f367r5-regulatory-source/v1',status='PREPARED_UNQUALIFIED',source_pins=pins,baseline_source=str(SRC),baseline_pins=previous['source_pins'],changed_files=changed,physical_prerequisite=previous['physical_prerequisite'],hardware_actions=False,userspace_pins={str(p):sha(p) for p in (DST/'userspace').iterdir()},producer_and_layout_pins={str(p):sha(p) for p in authority})
 (DST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(source=str(DST),overlay=str(OVERLAY),changed_files=changed)))
if __name__=='__main__':main()
