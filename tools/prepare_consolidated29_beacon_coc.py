"""Combine qualified SOURCE25 CoC with exact R12 beacon/APP/capability paths.

No491/PM removal, 449/461 integration, originals mutation, modules or hardware.
Every existing comment and inherited25 table record remains preserved.
"""
import argparse,hashlib,json,shutil,difflib
from collections import Counter
from pathlib import Path
from catalog_hgw_firmware_comments import scan_comments
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replace(text,ref,name):
 old=function(text,name+'(');new=function(ref,name+'(');assert text.count(old)==1;return text.replace(old,new,1)
def block(text,proc,name):
 body=function(text,proc+'(');start=body.index('\tcase '+name+':');end=body.index('\n\tcase ',start+1);return body[start:end]
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--beacon',type=Path,required=True);p.add_argument('--base-qualified',type=Path,required=True);p.add_argument('--beacon-qualified',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 assert json.loads((a.base/'result.json').read_text())['total_original_entries_added']==25;assert json.loads(a.base_qualified.read_text())['status']=='PASS_INDEPENDENT_OFFLINE_COC25_INITIALIZED_RETAINED_IC_SEVEN_MODULE_REVIEW';assert json.loads(a.beacon_qualified.read_text())['status']=='PASS_OFFLINE_R12_492_493_RECORD_RECOVERY_WITH_EXPLICIT_ADVERTISEMENT_DEVIATIONS'
 a.output.mkdir(parents=True);shutil.copytree(a.base/'source',a.output/'source');shutil.copytree(a.base/'headers',a.output/'headers')
 for name in ['ieee80211_beacon.c','ieee80211_beacon_desc.c','ieee80211_output.c']:shutil.copyfile(a.beacon/'source/wlan'/name,a.output/'source/wlan'/name)
 for name,tree,func in [('ieee80211.c','source/wlan','ieee80211_vap_remove_ie'),('qdrv_wlan.c','source/qdrv','qdrv_wlan_80211_beacon_update_run')]:
  dst=a.output/tree/name;dst.write_text(replace(dst.read_text(),(a.beacon/tree/name).read_text(),func),newline='\n')
 dst=a.output/'source/wlan/ieee80211_wireless.c';text=dst.read_text();ref=(a.beacon/'source/wlan/ieee80211_wireless.c').read_text();text=text.replace('#include <linux/version.h>','#include <linux/version.h>\n#include "openmitrastar_bss_tm.h"',1);text=text.replace('#define OM_OEM_PARAM_FIX_LEGACY_RATE 490','#define OM_OEM_PARAM_FIX_LEGACY_RATE 490\n#define OM_OEM_PARAM_NEIGHBOR_REPORT 492\n#define OM_OEM_PARAM_BSS_TM 493',1)
 for name in ['add_app_ie','remove_app_ie','get_app_ie']:text=replace(text,ref,name)
 for proc,switch in [('ieee80211_ioctl_setparam','\tswitch (param) {'),('ieee80211_ioctl_getparam','\tswitch (param[0] & 0xffff) {')]:
  old=function(text,proc+'(');blocks='\n'.join(block(ref,proc,name)for name in ['OM_OEM_PARAM_NEIGHBOR_REPORT','OM_OEM_PARAM_BSS_TM']);new=old.replace(switch,switch+'\n'+blocks,1);assert old!=new;text=text.replace(old,new,1)
 records=[]
 for name in ['bss_tm','get_bss_tm','neigh_repo','get_neigh_repo']:
  pos=ref.index('"'+name+'"');start=ref.rfind('\t{ ',0,pos);end=ref.index('},',pos)+2;records.append(ref[start:end])
 marker='\n};\n\nstatic const iw_handler ieee80211_handlers[]';assert text.count(marker)==1;text=text.replace(marker,'\n'+'\n'.join(records)+marker,1);dst.write_text(text,newline='\n')
 shutil.copyfile(a.beacon/'source/wlan/openmitrastar_bss_tm.h',a.output/'source/wlan/openmitrastar_bss_tm.h')
 for name in ['ieee80211_beacon_desc.h','ieee80211_proto.h']:shutil.copyfile(a.beacon/'headers/net80211'/name,a.output/'headers/net80211'/name)
 dst=a.output/'headers/net80211/ieee80211_var.h';text=dst.read_text();anchor='\tint om_coc_completed_level;\n';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\t/* Recovered OEM493 host-only state after inheritedCoC20byte state. */\n\tu32 om_bss_tm_flags;\n\t/* Recovered OEM492 NeighborReport advertisement state. */\n\tu32 om_neighbor_report_flags;\n',1);dst.write_text(text,newline='\n')
 # EveryCoC helper/dispatcherblock/ifacequiesce remains byte-for-byte source.
 basew=(a.base/'source/wlan/ieee80211_wireless.c').read_text();neww=(a.output/'source/wlan/ieee80211_wireless.c').read_text();basepm=(a.base/'source/wlan/ieee80211.c').read_text();newpm=(a.output/'source/wlan/ieee80211.c').read_text()
 for name in ['om_fix_legacy_rate','om_nac_prefix_sample']:assert function(basew,name+'(')==function(neww,name+'(')
 for proc in ['ieee80211_ioctl_setparam','ieee80211_ioctl_getparam']:assert block(basew,proc,'OM_OEM_PARAM_COC_MOVE_NDFS')==block(neww,proc,'OM_OEM_PARAM_COC_MOVE_NDFS')
 for name in ['om_coc_finish_csa','om_coc_publish_completion','om_ieee80211_coc_quiesce','om_coc_channel_switch','om_coc_update_pm','ieee80211_update_pm','om_coc_pm_queue','ieee80211_pm_queue_work','om_ieee80211_pm_queue_node_join','ieee80211_ifattach','ieee80211_ifdetach']:assert function(basepm,name+'(')==function(newpm,name+'('),name
 assert function((a.base/'source/qdrv/qdrv_wlan.c').read_text(),'qdrv_wlan_80211_exit(')==function((a.output/'source/qdrv/qdrv_wlan.c').read_text(),'qdrv_wlan_80211_exit(')
 assert sha(a.base/'source/wlan/ieee80211_node.c')==sha(a.output/'source/wlan/ieee80211_node.c')
 assert sha(a.base/'source/qdrv/qdrv_wlan.h')==sha(a.output/'source/qdrv/qdrv_wlan.h')
 comments={};patches=[]
 for tree in ['source/qdrv','source/wlan','headers']:
  for path in(a.base/tree).rglob('*'):
   if not path.is_file():continue
   new=a.output/path.relative_to(a.base);x,y=path.read_bytes(),new.read_bytes();c=lambda raw:Counter(raw[r['offset']:r['end_offset']]for r in scan_comments(raw));assert not c(x)-c(y),'oldcommentslost '+str(path)
   if x!=y:comments[str(path.relative_to(a.base))]=sum(c(x).values());patches.append(''.join(difflib.unified_diff(x.decode().splitlines(True),y.decode().splitlines(True),fromfile='a/'+str(path.relative_to(a.base)),tofile='b/'+str(path.relative_to(a.base)))))
 (a.output/'consolidation.patch').write_text(''.join(patches));files={str(p.relative_to(a.output)):sha(p)for tree in ['source','headers']for p in(a.output/tree).rglob('*')if p.is_file()}
 result={'schema':'openmitrastar.consolidated29-source/v1','status':'SOURCE_ONLY_CONSOLIDATED29_COC25_BEACON_R12_PENDING_ABI_MODULES','hardware_accessed':False,'firmware_eligible':False,'base':str(a.base),'beacon':str(a.beacon),'inherited_records':25,'added_records':4,'combined_source_records':29,'qualified_combined_records':None,'fullfunctional_driver_ops':None,'excluded':['449','461'],'preserved_CoC_source_helpers':True,'old_comments_preserved':comments,'files':files,'pins':{str(p):sha(p)for p in[Path(__file__),a.base/'result.json',a.beacon/'result.json',a.base_qualified,a.beacon_qualified]},'limits':['Source29privateRECORDS only; fullABIprefix/embedding/modules2x/matchedcontrolrequired.','CoCinitializedretainedIC scope/NACsnapshot/2unsupported and492/493advertisementdeviationspreserved.','NoRFclienttrafficbootpersistence/recovery/releaseacceptance.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'files':len(files),'source_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
