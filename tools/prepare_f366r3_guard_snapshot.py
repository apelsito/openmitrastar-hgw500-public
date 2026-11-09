"""Prepare cached-RAM native guard diagnostics and bind the real radar_bw producer."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f366r2';DST=ROOT/'work/kernel-port/f366r3'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def main():
 require(not DST.exists(),'immutable F366r3 source exists');DST.mkdir(parents=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(SRC/sub,DST/sub)
 p=DST/'qdrv/qdrv/qdrv_control.c';s=p.read_text()
 old='''  struct qdrv_mac *native_mac=qdrv_control_mac_get(dev,"0");
  struct qdrv_wlan *native_wlan=native_mac?qdrv_control_wlan_get(native_mac):NULL;
  if(!openmitrastar_sequential_started||!openmitrastar_sequential_vap_created||
     f366_native_radar_attempted||argc!=3||strcmp(argv[0],"radar")||
     strcmp(argv[1],"enable")||strcmp(argv[2],"eu"))return -EPERM;
  if(!native_wlan||native_wlan->ic.ic_opmode!=IEEE80211_M_HOSTAP||
     !native_wlan->ic.ic_curchan||native_wlan->ic.ic_curchan==IEEE80211_CHAN_ANYC||
     native_wlan->ic.ic_curchan->ic_ieee!=36||native_wlan->ic.ic_radar_bw!=80)return -EPERM;'''
 new='''  struct qdrv_mac *native_mac=qdrv_control_mac_get(dev,"0");
  struct qdrv_wlan *native_wlan=native_mac?qdrv_control_wlan_get(native_mac):NULL;
  struct ieee80211_channel *native_channel=NULL;
  int native_opmode=-1,native_radar_bw=-1,native_phymode=-1;
  unsigned native_ieee=0;
  bool native_valid_channel=false;
  bool native_args=argc==3&&!strcmp(argv[0],"radar")&&
   !strcmp(argv[1],"enable")&&!strcmp(argv[2],"eu");
  const char *native_reason="allow";
  /* Cached software fields only: no get_bw/MuC request, MMIO or new setter. */
  if(native_wlan){
   native_opmode=READ_ONCE(native_wlan->ic.ic_opmode);
   native_radar_bw=READ_ONCE(native_wlan->ic.ic_radar_bw);
   native_phymode=READ_ONCE(native_wlan->ic.ic_phymode);
   native_channel=READ_ONCE(native_wlan->ic.ic_curchan);
   native_valid_channel=native_channel&&native_channel!=IEEE80211_CHAN_ANYC;
   if(native_valid_channel)native_ieee=READ_ONCE(native_channel->ic_ieee);
  }
  if(!openmitrastar_sequential_started)native_reason="core-not-started";
  else if(!openmitrastar_sequential_vap_created)native_reason="vap-not-created";
  else if(f366_native_radar_attempted)native_reason="attempt-already-used";
  else if(!native_args)native_reason="command-not-exact-eu";
  else if(!native_mac)native_reason="missing-mac";
  else if(!native_wlan)native_reason="missing-wlan";
  else if(native_opmode!=IEEE80211_M_HOSTAP)native_reason="not-ap";
  else if(!native_valid_channel)native_reason="invalid-channel";
  else if(native_ieee!=36)native_reason="not-channel36";
  else if(native_radar_bw!=80)native_reason="radar-filter-not-80";
  pr_info("OMF366_NATIVE_GUARD revision=3 reason=%s core_started=%u vap_created=%u attempt_used=%u args_eu=%u mac_present=%u wlan_present=%u opmode=%d channel_valid=%u channel=%u radar_bw=%d phymode=%d reads=ram-only\\n",
   native_reason,!!openmitrastar_sequential_started,!!openmitrastar_sequential_vap_created,
   !!f366_native_radar_attempted,!!native_args,!!native_mac,!!native_wlan,
   native_opmode,!!native_valid_channel,native_ieee,native_radar_bw,native_phymode);
  if(strcmp(native_reason,"allow"))return -EPERM;'''
 require(s.count(old)==1,'R2 guard block changed');p.write_bytes(s.replace(old,new,1).encode())
 wlan=ROOT/'work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c'
 oem=ROOT/'work/sources/Quantenna-GPL/buildroot/target/device/Quantenna/Ruby/scripts/start-vap'
 enum=ROOT/'work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h'
 module=ROOT/'work/linux510-radio-port/quantenna/wlan/wlan.ko'
 installed=Path('/workspace/OpenMitraStar-build/f366/f366-components-20260922T093407Z/baseline-rootfs/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/wlan.ko')
 require(sha(module)==sha(installed)=='f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f','actual peer module identity drift')
 case='case IEEE80211_PARAM_RADAR_BW:\n\t\tic->ic_radar_bw = value;\n\t\tbreak;'
 require(case in wlan.read_text() and wlan.read_text().count('ic->ic_radar_bw =')==1,'radar_bw producer changed')
 require('iwpriv wifi0 radar_bw 80' in oem.read_text() and 'BW_HT80 = 80' in enum.read_text(),'OEM80 units changed')
 pins={p.relative_to(DST).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (DST/sub).rglob('*') if p.is_file()}
 baseline={p.relative_to(SRC).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (SRC/sub).rglob('*') if p.is_file()}
 changed=[n for n in pins if pins[n]!=baseline.get(n)];require(changed==['qdrv/qdrv/qdrv_control.c'],'unrelated R3 source delta')
 report={'schema':'openmitrastar.f366r3-guard-source/v1','status':'PREPARED_STRICT_GUARD_CACHED_SNAPSHOT','source_pins':pins,'baseline_pins':baseline,'changed_files':changed,'hardware_actions':False,'guard_profile_unchanged':'AP36 BW80 exacteu once','producer_evidence':{str(p):sha(p) for p in (wlan,oem,enum,module,installed)},'radar_bw_meaning':'separate radar filter mode set by IEEE80211_PARAM_RADAR_BW=235; units20/40/80; not a live bandwidth getter','snapshot_reads':'cached RAM only; no ieee80211_get_bw query, MMIO or new hardware access','r2_failure_limit':'R2 omitted the OEM radar_bw setter, but no guard-field snapshot exists to attribute its actual rejection uniquely to that field'}
 (DST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':str(DST),'manifest_sha256':sha(DST/'source-manifest.json')}))
if __name__=='__main__':main()
