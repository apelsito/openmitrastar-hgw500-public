"""Integrate qualified449r3 into qualifiedcombined29 in a new SOURCE30.

Only source artifact creation; nomodules/hardware. Every29record/function
outside449selectedchanges and all existingcomments remains preserved.
"""
import argparse,hashlib,json,shutil,difflib
from collections import Counter
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
from catalog_hgw_firmware_comments import scan_comments
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--coex',type=Path,required=True);p.add_argument('--base-qualified',type=Path,required=True);p.add_argument('--coex-qualified',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();b=json.loads(a.base_qualified.read_text());c=json.loads(a.coex_qualified.read_text());assert b['status']=='PASS_OFFLINE_CONSOLIDATED29_RECORDS_SOURCE_MODULE_CHECKPOINT'and b['offline_original_records_reconstructed']==29;assert c['status']=='PASS_OFFLINE_COEX26_R3_OEM_BSS_GEOMETRY_TIMER_RX_BW_MODULE_CLOSURE'and c['original_records_recovered']==26 and c['geometry_pair_cases']==33030144
 a.output.mkdir(parents=True);shutil.copytree(a.base/'source',a.output/'source');shutil.copytree(a.base/'headers',a.output/'headers')
 # Input/source29 kept SOURCE25body: whole449input/newnode overlay is exact
 # selected449change plus preservedsameCoCnodejoin. No492/493inputconsumer.
 for name in ['ieee80211_input.c','ieee80211_node.c']:shutil.copyfile(a.coex/'source/wlan'/name,a.output/'source/wlan'/name)
 dst=a.output/'source/qdrv/qdrv_wlan.c';text=dst.read_text();needle='\tic->ic_obss_scan_enable = 1;';assert text.count(needle)==1;text=text.replace(needle,'\tic->om_20_40_bss_coex = 1;\n'+needle,1);dst.write_text(text,newline='\n')
 dst=a.output/'source/wlan/ieee80211_wireless.c';text=dst.read_text();ref=(a.coex/'source/wlan/ieee80211_wireless.c').read_text();text=text.replace('#define OM_OEM_PARAM_COC_MOVE_NDFS 491','#define OM_OEM_PARAM_20_40_BSS_COEX 449\n#define OM_OEM_PARAM_COC_MOVE_NDFS 491',1)
 old=function(text,'void ieee80211_start_obss_scan_timer(');new=function(ref,'void ieee80211_start_obss_scan_timer(');assert old!=new and '!READ_ONCE(ic->om_20_40_bss_coex)'in new;text=text.replace(old,new,1);start=ref.index('\tcase OM_OEM_PARAM_20_40_BSS_COEX:');end=ref.index('\n\tcase ',start+1);setcase=ref[start:end];old=function(text,'ieee80211_ioctl_setparam(');new=old.replace('\tswitch (param) {','\tswitch (param) {\n'+setcase,1);assert new!=old;text=text.replace(old,new,1)
 pos=ref.index('"20_40_bss_coex"');start=ref.rfind('\t{ ',0,pos);end=ref.index('},',pos)+2;record=ref[start:end];marker='\n};\n\nstatic const iw_handler ieee80211_handlers[]';assert text.count(marker)==1;text=text.replace(marker,'\n'+record+marker,1);dst.write_text(text,newline='\n')
 dst=a.output/'headers/net80211/ieee80211_var.h';text=dst.read_text();needle='\tbool om_coc_pm_pending;\n';assert text.count(needle)==1;text=text.replace(needle,'\tbool om_coc_pm_pending; u8 om_20_40_bss_coex; /* OEM449: prior padding. */\n',1);proto='void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap);';assert text.count(proto)==1;text=text.replace(proto,proto+' void om_ieee80211_change_bw(struct ieee80211vap *vap,int bw,int delay_ch_switch);',1);dst.write_text(text,newline='\n')
 # AllCoC/legacy/NAC/APPhandlers identical; capsourceconsumers neverreplaced.
 basewire=(a.base/'source/wlan/ieee80211_wireless.c').read_text();newwire=(a.output/'source/wlan/ieee80211_wireless.c').read_text()
 for name in ['om_fix_legacy_rate','om_nac_prefix_sample','add_app_ie','remove_app_ie','get_app_ie']:assert function(basewire,name+'(')==function(newwire,name+'(')
 for name in ['ieee80211_beacon.c','ieee80211_beacon_desc.c','ieee80211_output.c','ieee80211.c']:assert sha(a.base/'source/wlan'/name)==sha(a.output/'source/wlan'/name)
 assert function((a.base/'source/qdrv/qdrv_wlan.c').read_text(),'qdrv_wlan_80211_beacon_update_run(')==function((a.output/'source/qdrv/qdrv_wlan.c').read_text(),'qdrv_wlan_80211_beacon_update_run(')
 comments={};patches=[]
 for tree in ['source/qdrv','source/wlan','headers']:
  for path in(a.base/tree).rglob('*'):
   if not path.is_file():continue
   new=a.output/path.relative_to(a.base);x,y=path.read_bytes(),new.read_bytes();cs=lambda raw:Counter(raw[r['offset']:r['end_offset']]for r in scan_comments(raw));assert not cs(x)-cs(y),'oldcommentlost '+str(path)
   if x!=y:comments[str(path.relative_to(a.base))]=sum(cs(x).values());patches.append(''.join(difflib.unified_diff(x.decode().splitlines(True),y.decode().splitlines(True),fromfile='a/'+str(path.relative_to(a.base)),tofile='b/'+str(path.relative_to(a.base)))))
 (a.output/'coex449-consolidation.patch').write_text(''.join(patches));files={str(p.relative_to(a.output)):sha(p)for tree in ['source','headers']for p in(a.output/tree).rglob('*')if p.is_file()};result={'status':'SOURCE_ONLY_CONSOLIDATED30_WITH_QUALIFIED449R3_PENDING_ABI_MODULES','schema':'openmitrastar.consolidated30-source/v1','hardware_accessed':False,'firmware_eligible':False,'base':str(a.base),'coex':str(a.coex),'combined_source_records':30,'qualified_combined_records':None,'fullfunctional_ops':None,'excluded':['461'],'old_comments_preserved':comments,'files':files,'pins':{str(p):sha(p)for p in[Path(__file__),a.base/'result.json',a.coex/'result.json',a.base_qualified,a.coex_qualified]},'limits':['SOURCE30only;449r3actualgeo/parsersemantics preservedbutcombinedABI/modulepairedglobalrequired.','InheritedCoC/NAC/492493safetydeviationsandtwofaithfulunsupportedrecords remain.','NoRFclienttrafficcoldbootpersistence/rollback/recovery/releaseacceptance.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'source_result_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
