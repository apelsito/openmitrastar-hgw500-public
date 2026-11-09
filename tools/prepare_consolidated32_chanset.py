"""NewSOURCE32 exact461r15scanner overlay ontoqualified30r2, offlineonly.

Preserves449timer/BSSgeometry,491PMqueue/stop,492493APP/cap paths andallcomments.
KeepsoneexistingBWhelper inieee80211_node; no duplicateexportfromr15wireless.
"""
import argparse,hashlib,json,shutil,difflib
from collections import Counter
from pathlib import Path
from catalog_hgw_firmware_comments import scan_comments
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def block(text,proc,label):
 body=function(text,proc+'(');start=body.index('\tcase '+label+':');end=body.index('\n\tcase ',start+1);return body[start:end]
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--scanner',type=Path,required=True);p.add_argument('--base-qualified',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();assert json.loads(a.base_qualified.read_text())['status']=='PASS_OFFLINE_CONSOLIDATED30_R2_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT';assert sha(a.scanner/'source/wlan/ieee80211_scan.c')=='539ba2dc423ea36feaf4151411bda59c2ba8c07503a1241dfaa38c29fad7f266';a.output.mkdir(parents=True);shutil.copytree(a.base/'source',a.output/'source');shutil.copytree(a.base/'headers',a.output/'headers')
 for name in ['ieee80211_scan.c','ieee80211_scan_ap.c','ieee80211_proto.c','openmitrastar_chanset_kernel.inc','openmitrastar_chanset_recovered.c','openmitrastar_chanset_recovered.h','openmitrastar_chanset_tables.h']:shutil.copyfile(a.scanner/'source/wlan'/name,a.output/'source/wlan'/name)
 ap=a.output/'source/wlan/ieee80211_scan_ap.c';text=ap.read_text();needle='return om_chanset_kernel_allowed(vap)?om_chanset_kernel_finished(ic):0; /* recovered scan queue */';assert text.count(needle)==1;text=text.replace(needle,needle+' /* restart scan */',1);ap.write_text(text,newline='\n')
 # Preservecombined30varheader entirely: it alreadydeclaresBWhelper.
 shutil.copyfile(a.scanner/'headers/net80211/ieee80211_scan.h',a.output/'headers/net80211/ieee80211_scan.h')
 dst=a.output/'source/wlan/ieee80211_wireless.c';text=dst.read_text();ref=(a.scanner/'source/wlan/ieee80211_wireless.c').read_text();anchor='#define OM_OEM_PARAM_20_40_BSS_COEX 449';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\n#define OM_OEM_PARAM_BW_AUTOSEL 461',1)
 for proc,switch in [('ieee80211_ioctl_setparam','\tswitch (param) {'),('ieee80211_ioctl_getparam','\tswitch (param[0] & 0xffff) {')]:
  old=function(text,proc+'(');case=block(ref,proc,'OM_OEM_PARAM_BW_AUTOSEL');new=old.replace(switch,switch+'\n'+case,1);assert old!=new;text=text.replace(old,new,1)
 entries=[]
 for name in ['set_bw_autosel','get_bw_autosel']:
  pos=ref.index('"'+name+'"');start=ref.rfind('\t{',0,pos);end=ref.index('},',pos)+2;entries.append(ref[start:end])
 marker='\n};\n\nstatic const iw_handler ieee80211_handlers[]';assert text.count(marker)==1;text=text.replace(marker,'\n'+'\n'.join(entries)+marker,1);dst.write_text(text,newline='\n')
 # Actualcurrenttimer+CAPAPPhelpers andevery25/30state remainexact.
 basew=(a.base/'source/wlan/ieee80211_wireless.c').read_text();neww=dst.read_text()
 for name in ['void ieee80211_start_obss_scan_timer','static int om_fix_legacy_rate','static int om_nac_prefix_sample','static int\nadd_app_ie','static int\nremove_app_ie','static int\nget_app_ie']:assert function(basew,name+'(')==function(neww,name+'('),name
 for proc in ['ieee80211_ioctl_setparam','ieee80211_ioctl_getparam']:
  for name in ['OM_OEM_PARAM_COC_MOVE_NDFS','OM_OEM_PARAM_NEIGHBOR_REPORT','OM_OEM_PARAM_BSS_TM']:assert block(basew,proc,name)==block(neww,proc,name)
 assert block(basew,'ieee80211_ioctl_setparam','OM_OEM_PARAM_20_40_BSS_COEX')==block(neww,'ieee80211_ioctl_setparam','OM_OEM_PARAM_20_40_BSS_COEX')
 for name in ['ieee80211.c','ieee80211_beacon.c','ieee80211_beacon_desc.c','ieee80211_output.c','ieee80211_node.c','ieee80211_input.c']:assert sha(a.base/'source/wlan'/name)==sha(a.output/'source/wlan'/name)
 assert sha(a.base/'source/qdrv/qdrv_wlan.c')==sha(a.output/'source/qdrv/qdrv_wlan.c');assert sha(a.base/'headers/net80211/ieee80211_var.h')==sha(a.output/'headers/net80211/ieee80211_var.h')
 comments={};patches=[]
 for root in ['source/qdrv','source/wlan','headers']:
  for before in(a.base/root).rglob('*'):
   if not before.is_file():continue
   after=a.output/before.relative_to(a.base);x,y=before.read_bytes(),after.read_bytes();c=lambda raw:Counter(raw[z['offset']:z['end_offset']]for z in scan_comments(raw));assert not c(x)-c(y),'oldcommentslost '+str(before)
   if x!=y:comments[str(before.relative_to(a.base))]=sum(c(x).values());patches.append(''.join(difflib.unified_diff(x.decode().splitlines(True),y.decode().splitlines(True),fromfile='a/'+str(before.relative_to(a.base)),tofile='b/'+str(before.relative_to(a.base)))))
 (a.output/'consolidated461-overlay.patch').write_text(''.join(patches));files={str(p.relative_to(a.output)):sha(p)for root in ['source','headers']for p in(a.output/root).rglob('*')if p.is_file()};r={'status':'SOURCE_ONLY_CONSOLIDATED32_WITH_461_R15_PENDING_SCANNER_ABI_MODULES','schema':'openmitrastar.consolidated32-source/v1','hardware_accessed':False,'firmware_eligible':False,'base':str(a.base),'scanner':str(a.scanner),'source_original_records':32,'qualified_combined_records':None,'fullfunctional_ops':None,'old_comments_preserved':comments,'scanner_exact_r15':True,'shared_HOST_IC_ABIheader_exact30':True,'single_BWhelper_existing_node':True,'files':files,'pins':{str(p):sha(p)for p in[Path(__file__),a.base/'result.json',a.scanner/'result.json',a.base_qualified,a.review]},'limits':['SOURCE32only;461scheduler/scannerprivateABI andallconsumerspairedcompile/globaldelta required.','ExactUP/PREEMPT_NONEreviewscope; sharedscalarsnotcoherenttuple, noforeigncallerlifetime claim.','Existing449/491/492493/NAC/2unsupported limitations retained; noRFclienttrafficpersistence/recovery/release.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'files':len(files),'source_manifest_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
