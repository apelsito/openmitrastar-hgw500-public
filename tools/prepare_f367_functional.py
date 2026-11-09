"""Prepare the proof-bound AP52/20 F367 source from the accepted R3 bootstrap."""
from pathlib import Path
import hashlib,json,shutil
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/kernel-port/f367-r3-bootstrap';DEST=ROOT/'work/kernel-port/f367-functional'
PROOF=ROOT/'outputs/acceptance/f366r3-acquisition-addendum-20260922T114659Z/result.json'
PROOF_SHA='9201514a074decb9987cdaa174f25c19739ddc083e9a842179fec77cc633fb87'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def once(s,a,b):require(s.count(a)==1,'ambiguous anchor '+a[:75]);return s.replace(a,b,1)
def function(s,name,replacement):return once(s,extract(s,name),replacement+'\n')
def main():
 require(sha(PROOF)==PROOF_SHA,'exact R3 acceptance required');proof=json.loads(PROOF.read_text())
 require(proof['status']=='PASS_F366R3_NATIVE_ACQUISITION_WITH_F365_RETURN_ADDENDUM' and proof['containment_confirmed'] and proof['watchdog_reset_observed'] and proof['f365_return_platform_checks']==27,'R3 physical prerequisites')
 for p,h in proof['evidence'].items():require(sha(p)==h,'physical evidence drift '+p)
 require(not (DEST/'source-manifest.json').exists(),'immutable functional source exists');DEST.mkdir(parents=True,exist_ok=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(BASE/sub,DEST/sub,dirs_exist_ok=True)
 (DEST/'kernel/f367_build_gate.h').write_bytes(('/* Controlled AP DFS build, not regulatory release certification. */\n#define F367_NATIVE_AUTHORITY_BUILD 1\n#define F367_ACQUISITION_EVIDENCE_SHA256 "'+PROOF_SHA+'"\n').encode())
 shutil.copyfile(ROOT/'tools/f367_provider_context.inc',DEST/'kernel/f367_context.inc')
 p=DEST/'kernel/f332_provider.c';s=p.read_text();s=once(s,'int radar_set_chan(uint8_t channel)', '#include "f367_context.inc"\nint radar_set_chan(uint8_t channel)')
 s=once(s,'struct f341_ipc_stats ipc;','struct f341_ipc_stats ipc;')
 s=once(s,'seq_puts(s,"disable_contract=', 'seq_printf(s,"authority_build=%u\\nauthoritative_enabled=%u\\nfilter_bandwidth=%u\\n",F367_NATIVE_AUTHORITY_BUILD,authoritative_enable,requests.bandwidth);\n seq_puts(s,"disable_contract=')
 s+='\nMODULE_INFO(acquisition_evidence,F367_ACQUISITION_EVIDENCE_SHA256);\n';p.write_bytes(s.encode())
 q=DEST/'qdrv/qdrv';shutil.copyfile(ROOT/'tools/f367_qdrv_control.inc',q/'qdrv_f367_control.inc')
 p=q/'qdrv_f367_ap.inc';s=p.read_text()
 s=once(s,'static struct f367_ap_policy f367_policy;','''static struct f367_ap_policy f367_policy;
static bool f367_control_fault,f367_transition_prepared,f367_on_dfs,f367_switch_inflight;
static unsigned f367_software_injections,f367_native_callbacks;
static u64 f367_quarantine_start_ns,f367_quarantine_deadline_ns;
static u64 f367_cac_start_ns,f367_cac_deadline_ns,f367_nop_start_ns,f367_nop_deadline_ns;''')
 s=once(s,'if(!ic||(chan=ic->ic_curchan)==NULL||chan==IEEE80211_CHAN_ANYC)return false;',
  'if(!ic||READ_ONCE(f367_control_fault)||READ_ONCE(f367_transition_prepared)||READ_ONCE(f367_switch_inflight)||(chan=ic->ic_curchan)==NULL||chan==IEEE80211_CHAN_ANYC)return false;')
 s=once(s,' spin_unlock_irqrestore(&f367_policy_lock,flags);return result;\n}\nstatic bool qdrv_f367_cac_begin',
  ' if(chan->ic_ieee==52&&(ktime_get_ns()<f367_quarantine_deadline_ns||ktime_get_ns()<f367_cac_deadline_ns||(f367_policy.nop&&ktime_get_ns()<f367_nop_deadline_ns)))result=false;\n spin_unlock_irqrestore(&f367_policy_lock,flags);return result;\n}\nstatic bool qdrv_f367_cac_begin')
 s=once(s,'result=qdrv_f367_ap()&&f367_begin_cac(&f367_policy,(u32)jiffies,HZ,READ_ONCE(qdrv_f332.cac_generation),chan->ic_ieee,ic->ic_radar_bw);',
  'result=qdrv_f367_ap()&&ktime_get_ns()>=f367_quarantine_deadline_ns&&(!f367_policy.nop||ktime_get_ns()>=f367_nop_deadline_ns)&&f367_begin_cac(&f367_policy,(u32)jiffies,HZ,READ_ONCE(qdrv_f332.cac_generation),chan->ic_ieee,ic->ic_radar_bw);\n if(result){f367_cac_start_ns=ktime_get_ns();f367_cac_deadline_ns=f367_cac_start_ns+70000000000ULL;}')
 s=once(s,'result=qdrv_f367_ap()&&f367_finish_cac(', 'result=qdrv_f367_ap()&&ktime_get_ns()>=f367_cac_deadline_ns&&f367_finish_cac(')
 s=once(s,'f367_mark_radar(&f367_policy,(u32)jiffies,HZ);','f367_mark_radar(&f367_policy,(u32)jiffies,HZ);f367_nop_start_ns=ktime_get_ns();f367_nop_deadline_ns=f367_nop_start_ns+1800000000000ULL;')
 s=once(s,'if(!f367_policy.initialized)f367_policy_init(&f367_policy,(u32)jiffies,HZ);','if(!f367_policy.initialized){f367_policy_init(&f367_policy,(u32)jiffies,HZ);f367_quarantine_start_ns=ktime_get_ns();f367_quarantine_deadline_ns=f367_quarantine_start_ns+1800000000000ULL;}')
 p.write_bytes(s.encode())
 p=q/'qdrv_radar.c';s=p.read_text()
 s=once(s,'#include <linux/version.h>','#include <linux/version.h>\n#include <linux/moduleparam.h>\n#include <linux/ktime.h>\n#include <linux/math64.h>')
 s=once(s,'extern int radar_set_scan_context(uint8_t channel);','extern int radar_set_scan_context(uint8_t channel);\nextern int radar_set_context(uint8_t channel,uint32_t bandwidth);\nextern uint32_t radar_get_context(uint32_t*channel,uint32_t*bandwidth);')
 s=once(s,'#include "qdrv_f338_availability.inc"','#include "qdrv_f338_availability.inc"\n#include "qdrv_f367_control.inc"')
 s=once(s,'if (radar_set_scan_context(0) || radar_set_chan(new_chan->ic_ieee)) {',
  'if (!qdrv_f367_context_admit(new_chan) || radar_set_scan_context(0) || radar_set_context(new_chan->ic_ieee,ic->ic_radar_bw)) {')
 s=once(s,'\t/* check if radar detection on the channel is requried */','\t/* This callback runs after the direct setchan result or the MuC switch event. */\n\tWRITE_ONCE(f367_switch_inflight,false);\n\t/* check if radar detection on the channel is requried */')
 s=s.replace('expires = jiffies + CAC_WEATHER_PERIOD_EU;','expires = jiffies + CAC_WEATHER_PERIOD_EU + 1;').replace('expires = jiffies + CAC_PERIOD;','expires = jiffies + CAC_PERIOD + 1;').replace('expires = jiffies + 1800 * HZ;','expires = jiffies + 1800 * HZ + 1;')
 old=extract(s,'dfs_action');new=once(old,' sys_disable_xmit();',' WRITE_ONCE(f367_switch_inflight,true);\n sys_disable_xmit();');s=once(s,old,new)
 s=function(s,'mark_radar','''static void mark_radar(void)
{
 struct ieee80211com*ic=qdrv_radar_cb.ic;uint32_t channel=0,bw=0;
 uint32_t generation=radar_get_context(&channel,&bw);
 f367_native_callbacks++;
 if(!ic||!ic->ic_curchan||ic->ic_curchan==IEEE80211_CHAN_ANYC||
    !generation||generation!=radar_ready_generation()||channel!=52||bw!=20||
    ic->ic_curchan->ic_ieee!=channel||ic->ic_radar_bw!=bw){
  qdrv_f367_channel_fault(-ESTALE);return;
 }
 pr_info("OMF367_RADAR origin=NATIVE_PROVIDER generation=%u channel=52 bandwidth=20\\n",generation);
 qdrv_radar_detected(ic,0);
}''')
 p.write_bytes(s.encode())
 p=q/'qdrv_radar.h';p.write_bytes((p.read_text()+'\nvoid qdrv_f367_channel_fault(int error);\n').encode())
 p=q/'qdrv_wlan.c';s=p.read_text()
 s=once(s,'\tqdrv_hostlink_setchan(qw, freq_band, qtn_chan);','\t{int rc=qdrv_hostlink_setchan(qw,freq_band,qtn_chan);\n\t if(rc){qdrv_f367_channel_fault(rc);return;}}')
 s=once(s,'\tqdrv_hostlink_setchan_deferred(qw, sp->csa_bus);','\t{int rc=qdrv_hostlink_setchan_deferred(qw,sp->csa_bus);\n\t if(rc){qdrv_f367_channel_fault(rc);return;}}')
 p.write_bytes(s.encode())
 pins={p.relative_to(DEST).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (DEST/sub).rglob('*') if p.is_file()}
 base_pins={p.relative_to(BASE).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (BASE/sub).rglob('*') if p.is_file()}
 report={'schema':'openmitrastar.f367-functional-source/v1','status':'PREPARED_FOR_AFFECTED_CHECKS','physical_prerequisite':{'path':str(PROOF),'sha256':PROOF_SHA},'source_pins':pins,'baseline_source':str(BASE),'changed_files':sorted(n for n in pins if pins[n]!=base_pins.get(n)),'authority_build':1,'release_qualified':False,'profile':{'bootstrap_channel':36,'bootstrap_bw':80,'dfs_channel':52,'dfs_bw':20,'escape_channel':36,'quarantine_ms':1800000,'cac_ms':70000,'nop_ms':1800000},'hardware_actions':False,'classifier_preprocessor_acquisition_postfilter_changed':False}
 (DEST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':str(DEST),'changed_files':report['changed_files'],'proof':PROOF_SHA}))
if __name__=='__main__':main()
