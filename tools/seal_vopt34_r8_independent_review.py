"""Bound static independent VOPT34r8 adapter review; no module/hardware qualification."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();pins={}
 def read(p):pins[str(p)]=sha(p);return json.loads(p.read_text())
 r=read(a.candidate/'result.json');k=a.candidate/'source/wlan/openmitrastar_vopt481_kernel.inc';v=a.candidate/'source/qdrv/qdrv_vap.c';h=a.candidate/'source/qdrv/qdrv_hostlink.c';w=a.candidate/'source/wlan/ieee80211_wireless.c';kt=k.read_text();vt=v.read_text();ht=h.read_text();wt=w.read_text()
 assert 'if(!rtnl_trylock())goto no_rtnl;'in kt and 'if(current_work()==&ic->om_vopt_work)return -EBUSY;'in kt and 'if(rc==-EINPROGRESS)ic->om_vopt_stopping=true;'in kt
 assert 'if(!rtnl_is_locked()||in_interrupt()||irqs_disabled())return -EBUSY;'in kt and 'if(om_vopt_kernel_write_ready(ic,(unsigned)param))return -EBUSY;'in wt
 assert 'rtnl_lock();\n\tom_ieee80211_vopt_resume(ic);\n\trtnl_unlock();'in vt and 'ieee80211_vap_detach_late(&qv->iv);\n\tom_ieee80211_vopt_resume(om_vopt_ic);\n\trtnl_unlock();'in vt
 assert 'qdrv_f355_claim("vopt482")'in ht and 'try_module_get(THIS_MODULE)'in ht and 'if(cal_rc==-EINPROGRESS)goto retained;'in ht and 'if(normal_rc==-EINPROGRESS)goto retained;'in ht
 for x in[k,v,h,w,a.candidate/'source/qdrv/f355_lifetime.h',a.candidate/'source/qdrv/qdrv_f355_lifetime.c',a.candidate/'source/wlan/ieee80211.c']:pins[str(x)]=sha(x)
 receipts=[]
 for folder,status,count in [('vopt34-worker-fixture-20261022T213800Z-r8','PASS_ACTUAL_VOPT34_LINUX_WORKER_SOURCE_FAKE_CALLBACK_FIXTURE',14),('vopt34-timer-worker-owned-20261022T214200Z-r8','PASS_WHOLE_ACTUAL_IC_TIMER_WORKER_482_HELPER_F355_CORE_SOURCE_FIXTURE',3)]:
  rr=read(ROOT/'outputs/rea'/folder/'result.json');assert rr['status']==status and rr['cases']==count
  for path,d in rr['input_pins'].items():assert sha(path)==d;pins[path]=d
  receipts.append({'status':status,'cases':count})
 q=a.candidate/'source/qdrv/qdrv_wlan.c';assert 'if(qdrv_f355_retained())return -EBUSY;'in q.read_text();pins[str(q)]=sha(q)
 pins[str(Path(__file__))]=sha(__file__);assert all(sha(x)==d for x,d in pins.items());a.output.mkdir(parents=True);r={'status':'PASS_STATIC_INDEPENDENT_VOPT34_R8_ADAPTER_REVIEW_PENDING_PAIRED_MODULES','hardware_accessed':False,'firmware_eligible':False,'qualified_records_added':0,'candidate':str(a.candidate),'source_sha256':sha(a.candidate/'result.json'),'reviewed':receipts,'checks':['RTNLtrylock worker avoids VAP-delete syncjoin lock inversion.','current_work prevents self canceljoin; stopping/destroying distinguishes ordinary resume from permanent detach.','SavedIC resume at VAP latefree underRTNL; newVAP constructor resumes only underRTNL.','RelevantWEXT writes requireprocessRTNL/notrunning beforemutation; actualLinuxWEXTdispatch lock seen separately.','482unknownstages retainmodule/DMA/descriptor/IC owner and block414/reassoc; F355 prevents parent WLANfree.'],'limits':['Staticreviewandactualsourcehostfixtures only; notLinux scheduler/DMA/MuC concurrencyexecution.','Pairedfull58headerusers+ABI/control/allmodulecode/data/RELA/symbol/negative gates remain required.','Noallmetric/OEMuniversalbehavior,RF/client/traffic/persistence/releaseacceptance.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
