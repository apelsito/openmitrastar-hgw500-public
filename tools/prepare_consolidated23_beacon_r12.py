"""Combine exact SOURCE23 operations with qualified beacon R10/R11c source.

Preserves OEM498/484/457/490 and every old comment. Host IC appends BSS/neighbor
state after SOURCE23 legacy state; no SOURCE25/461/491 integration or hardware.
"""
import argparse,hashlib,json,shutil,difflib
from collections import Counter
from pathlib import Path
from catalog_hgw_firmware_comments import scan_comments
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replace_func(text,reference,name):
 old=function(text,name+'(');new=function(reference,name+'(');assert text.count(old)==1;return text.replace(old,new,1)
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--beacon',type=Path,required=True);p.add_argument('--beacon-qualified',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();assert json.loads((a.base/'result.json').read_text())['total_original_entries_added']==23;assert json.loads(a.beacon_qualified.read_text())['status']=='PASS_OFFLINE_R11C_COMPLETE_SEVEN_MODULE_APP_SYNC_SCOPE';a.output.mkdir(parents=True);shutil.copytree(a.base/'source',a.output/'source');shutil.copytree(a.base/'headers',a.output/'headers');touched=[]
 # WLAN beacon algorithms are identical outside declared recovered/beacon work.
 for name in ['ieee80211_beacon.c','ieee80211_beacon_desc.c','ieee80211_output.c']:
  dst=a.output/'source/wlan'/name;dst.write_bytes((a.beacon/'source/wlan'/name).read_bytes());touched.append(dst)
 # Preserve typed VAPsetup484 default while replacing only APP cleanup body.
 dst=a.output/'source/wlan/ieee80211.c';dst.write_text(replace_func(dst.read_text(),(a.beacon/'source/wlan/ieee80211.c').read_text(),'ieee80211_vap_remove_ie'),newline='\n');touched.append(dst)
 dst=a.output/'source/qdrv/qdrv_wlan.c';dst.write_text(replace_func(dst.read_text(),(a.beacon/'source/qdrv/qdrv_wlan.c').read_text(),'qdrv_wlan_80211_beacon_update_run'),newline='\n');touched.append(dst)
 # Wireless keeps all SOURCE23 helpers/setters/getters/table. Add4 BSS entries.
 dst=a.output/'source/wlan/ieee80211_wireless.c';text=dst.read_text();ref=(a.beacon/'source/wlan/ieee80211_wireless.c').read_text()
 text=text.replace('#include <linux/version.h>','#include <linux/version.h>\n#include "openmitrastar_bss_tm.h"',1)
 text=text.replace('#define OM_OEM_PARAM_FIX_LEGACY_RATE 490','#define OM_OEM_PARAM_FIX_LEGACY_RATE 490\n#define OM_OEM_PARAM_NEIGHBOR_REPORT 492\n#define OM_OEM_PARAM_BSS_TM 493',1)
 for name in ['add_app_ie','remove_app_ie','get_app_ie']:text=replace_func(text,ref,name)
 setbody=function(ref,'ieee80211_ioctl_setparam(');start=setbody.index('\tcase OM_OEM_PARAM_NEIGHBOR_REPORT:');end=setbody.index('\tcase OM_OEM_PARAM_CHECK_CURRENT_CHANNEL:',start);blocks=setbody[start:end]
 old=function(text,'ieee80211_ioctl_setparam(');new=old.replace('\tswitch (param) {','\tswitch (param) {\n'+blocks,1);assert new!=old;text=text.replace(old,new,1)
 getbody=function(ref,'ieee80211_ioctl_getparam(');start=getbody.index('\tcase OM_OEM_PARAM_NEIGHBOR_REPORT:');end=getbody.index('\tcase OM_OEM_PARAM_BBDF_WAR:',start);blocks=getbody[start:end]
 old=function(text,'ieee80211_ioctl_getparam(');new=old.replace('\tswitch (param[0] & 0xffff) {','\tswitch (param[0] & 0xffff) {\n'+blocks,1);assert old!=new;text=text.replace(old,new,1)
 start=ref.index('\t{ OM_OEM_PARAM_BSS_TM,');end=ref.index('\n};',start);records=ref[start:end];assert records.count('OM_OEM_PARAM_')==4
 marker='\n};\n\nstatic const iw_handler ieee80211_handlers[]';assert text.count(marker)==1;text=text.replace(marker,'\n'+records+marker,1);dst.write_text(text,newline='\n');touched.append(dst)
 shutil.copyfile(a.beacon/'source/wlan/openmitrastar_bss_tm.h',a.output/'source/wlan/openmitrastar_bss_tm.h')
 for name in ['ieee80211_beacon_desc.h','ieee80211_proto.h']:shutil.copyfile(a.beacon/'headers/net80211'/name,a.output/'headers/net80211'/name)
 dst=a.output/'headers/net80211/ieee80211_var.h';text=dst.read_text();anchor='\tint om_legacy_rate_fixed;\n';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\t/* Recovered OEM493 host-only state after SOURCE23 legacy fields. */\n\tu32 om_bss_tm_flags;\n\t/* Recovered OEM492 host-only NeighborReport capability state. */\n\tu32 om_neighbor_report_flags;\n',1);dst.write_text(text,newline='\n');touched.append(dst)
 # Explicit preservation of all SOURCE23 operations/header typedfield/state.
 basewire=(a.base/'source/wlan/ieee80211_wireless.c').read_text();newwire=(a.output/'source/wlan/ieee80211_wireless.c').read_text()
 for name in ['om_fix_legacy_rate','om_nac_prefix_sample']:assert function(basewire,name+'(')==function(newwire,name+'(')
 for token in ['OM_OEM_PARAM_DYNAMIC_SIFS','OM_OEM_PARAM_DUPLICATE_RTS','OM_OEM_PARAM_TX_AMSDU_11N','OM_OEM_PARAM_NAC_MODE','OM_OEM_PARAM_FIX_LEGACY_RATE']:assert newwire.count(token)==basewire.count(token)
 assert sha(a.output/'source/qdrv/qdrv_wlan.h')==sha(a.base/'source/qdrv/qdrv_wlan.h')
 assert function((a.output/'source/qdrv/qdrv_wlan.c').read_text(),'qdrv_wlan_80211_beacon_update_run(')==function((a.beacon/'source/qdrv/qdrv_wlan.c').read_text(),'qdrv_wlan_80211_beacon_update_run(')
 assert function((a.output/'source/wlan/ieee80211.c').read_text(),'ieee80211_vap_remove_ie(')==function((a.beacon/'source/wlan/ieee80211.c').read_text(),'ieee80211_vap_remove_ie(')
 assert 'u8 iv_tx_amsdu_11n;'in(a.output/'headers/net80211/ieee80211_var.h').read_text();assert 'vap->iv_tx_amsdu_11n = 1;'in(a.output/'source/wlan/ieee80211.c').read_text()
 comments={};patches=[]
 for tree in ['source/qdrv','source/wlan','headers']:
  for before in(a.base/tree).rglob('*'):
   if not before.is_file():continue
   after=a.output/before.relative_to(a.base);old=before.read_bytes();new=after.read_bytes();c=lambda raw:Counter(raw[x['offset']:x['end_offset']]for x in scan_comments(raw));assert not c(old)-c(new),'old comment lost '+str(before)
   if old!=new:comments[str(before.relative_to(a.base))]=sum(c(old).values());patches.append(''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='a/'+str(before.relative_to(a.base)),tofile='b/'+str(before.relative_to(a.base)))))
 (a.output/'consolidation.patch').write_text(''.join(patches))
 pins={str(p):sha(p)for p in[Path(__file__),a.base/'result.json',a.beacon/'result.json',a.beacon_qualified]};files={str(p.relative_to(a.output)):sha(p)for tree in['source','headers']for p in(a.output/tree).rglob('*')if p.is_file()}
 result={'schema':'openmitrastar.consolidated23-beacon-r12-source/v1','status':'SOURCE_ONLY_CONSOLIDATED23_BEACON_R10_R11C_PENDING_FULL_HEADER_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'base':str(a.base),'beacon':str(a.beacon),'inherited_SOURCE23_records':23,'added_BSS_neighbor_records':4,'combined_source_records':27,'qualified_combined_operation_count':None,'SOURCE25_491_461_included':False,'preserved_ops':['457NAC','463dynamicSIFS','484typedVAPAMSDU','490legacyrate','498duplicateRTS'],'old_comments_preserved':comments,'files':files,'source_pins':pins,'limits':['SOURCE19beaconlineagecombinedwithSOURCE23; full58unit2xABIembedding/wholemodulecontrolsrequired.','FouraddedBSS/neighborrecordsretainpartialsourcecapabilityscope; notfournewphysicalfunctionaloperations.','NohardwareRFclienttrafficbootpersistence/recovery/releaseacceptance.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'files':len(files),'changed_old_comment_files':len(comments),'result_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
