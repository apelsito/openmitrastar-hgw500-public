"""Recover OEM494/495 VAPstate and actual MDIE54 beacon/probe consumers.

Newsource35 onqualified32. NoFTauth/actionhandler claim; setter495low8 only
andget495faithfulunsupportedretained. Exactowneddescriptor/frame budgets.
"""
import argparse,hashlib,json,shutil,difflib
from collections import Counter
from pathlib import Path
from catalog_hgw_firmware_comments import scan_comments
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
HELPER=r'''#ifndef OPENMITRASTAR_MDIE_H
#define OPENMITRASTAR_MDIE_H
#include <linux/types.h>
/* Exact OEM IE54/length3: MDID little-endian bytes and nonzero FTOverDS bit0.
 * The caller reserves five owned frame bytes before invoking this producer. */
static inline u8 *om_mdie_write(u8 *frm,u16 mdid,u8 ft_over_ds)
{
    frm[0]=54;frm[1]=3;
    frm[2]=(u8)mdid;frm[3]=(u8)(mdid>>8);
    frm[4]=ft_over_ds?1U:0U;
    return frm+5;
}
#endif
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();assert json.loads(a.qualification.read_text())['status']=='PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT';a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
 dst=a.output/'headers/net80211/ieee80211_var.h';text=dst.read_text();anchor='\tu8 iv_tx_amsdu_11n;\n';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\t/* RecoveredOEM494/495 independentVAPstate after alloldmembers. */\n\tu16 om_mdid;\n\tu8 om_ft_over_ds;\n',1);dst.write_text(text,newline='\n')
 w=a.output/'source/wlan/ieee80211_wireless.c';text=w.read_text();anchor='#define OM_OEM_PARAM_FT_OVER_DS 495';assert text.count(anchor)==1;text=text.replace(anchor,'#define OM_OEM_PARAM_MDID 494\n'+anchor,1);start=text.index('\tswitch (param) {',text.index('ieee80211_ioctl_setparam('));text=text[:start]+text[start:].replace('\tswitch (param) {','''\tswitch (param) {
\tcase OM_OEM_PARAM_MDID:
\t\tif(vap->iv_opmode!=IEEE80211_M_HOSTAP)return -EINVAL;
\t\tWRITE_ONCE(vap->om_mdid,(u16)value);
\t\tic->ic_beacon_update(vap);
\t\treturn 0;
\tcase OM_OEM_PARAM_FT_OVER_DS:
\t\tif(vap->iv_opmode!=IEEE80211_M_HOSTAP)return -EINVAL;
\t\tWRITE_ONCE(vap->om_ft_over_ds,(u8)value);
\t\treturn 0;
''',1);start=text.index('\tswitch (param[0] & 0xffff) {',text.index('ieee80211_ioctl_getparam('));text=text[:start]+text[start:].replace('\tswitch (param[0] & 0xffff) {','\tswitch (param[0] & 0xffff) {\n\tcase OM_OEM_PARAM_MDID:\n\t\tparam[0]=(u16)READ_ONCE(vap->om_mdid);\n\t\tbreak;\n',1);marker='\n};\n\nstatic const iw_handler ieee80211_handlers[]';assert text.count(marker)==1;records='''
\t{OM_OEM_PARAM_MDID,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"mdid"},
\t{OM_OEM_PARAM_MDID,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"get_mdid"},
\t{OM_OEM_PARAM_FT_OVER_DS,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"ft_over_ds"},''';text=text.replace(marker,records+marker,1);w.write_text(text,newline='\n')
 (a.output/'source/wlan/openmitrastar_mdie.h').write_text(HELPER,newline='\n')
 for name in['ieee80211_beacon.c','ieee80211_beacon_desc.c','ieee80211_output.c']:
  dst=a.output/'source/wlan'/name;text=dst.read_text();anchor='#include "openmitrastar_bss_tm.h"';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\n#include "openmitrastar_mdie.h"',1)
  if name=='ieee80211_beacon.c':
   anchor='\t/* BSS load element */';assert text.count(anchor)==1;text=text.replace(anchor,'\tif(READ_ONCE(vap->om_mdid))\n\t\tfrm=ieee80211_add_beacon_desc_ie(ni,54,frm);\n\n'+anchor,1);anchor='\t\t + 7 /* RecoveredRRMIE70 descriptor reserve */';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\n\t\t + 5 /* OEM494 conditionalMDIE54 maximum */',1)
  elif name=='ieee80211_beacon_desc.c':
   anchor='\tswitch (ext_ie_id) {';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'''\n\tcase 54:
\t\tfrm=om_mdie_write(frm,READ_ONCE(vap->om_mdid),READ_ONCE(vap->om_ft_over_ds));
\t\tbreak;''',1)
  else:
   anchor='IEEE80211_APPIE_MAX + 7 /* recoveredRRMIE reserve */';assert text.count(anchor)==2;text=text.replace(anchor,anchor+' + 5 /* OEM494MDIEreserveforprobe */',1)
   # OEM send_mgmt MDIE only PROBE_RESP, before AthAdvCaps, conditionalMDID.
   start=text.index('case IEEE80211_FC0_SUBTYPE_PROBE_RESP:');end=text.index('case IEEE80211_FC0_SUBTYPE_AUTH:',start);part=text[start:end];anchor='\t\t/* AthAdvCaps */';assert part.count(anchor)==1;part=part.replace(anchor,'\t\tif(READ_ONCE(vap->om_mdid))\n\t\t\tfrm=om_mdie_write(frm,READ_ONCE(vap->om_mdid),READ_ONCE(vap->om_ft_over_ds));\n\n'+anchor,1);text=text[:start]+part+text[end:]
  dst.write_text(text,newline='\n')
 # ParentVAPkzalloc/zeroing initialization coversnewtail; runtimeallocation
 # is sizeof qdrv_vap and requiresfullheaderclosurebeforemodulepromotion.
 changes={};comments={};patch=[]
 for tree in['source','headers']:
  for before in(a.parent/tree).rglob('*'):
   if not before.is_file():continue
   after=a.output/before.relative_to(a.parent);x,y=before.read_bytes(),after.read_bytes();c=lambda raw:Counter(raw[r['offset']:r['end_offset']]for r in scan_comments(raw));assert not c(x)-c(y),'oldcommentslost '+str(before)
   if x!=y:rel=str(before.relative_to(a.parent));changes[rel]=sha(after);comments[rel]=sum(c(x).values());patch.extend(difflib.unified_diff(x.decode().splitlines(True),y.decode().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 (a.output/'mdid-ft-recovery.patch').write_text(''.join(patch));files={str(p.relative_to(a.output)):sha(p)for tree in['source','headers']for p in(a.output/tree).rglob('*')if p.is_file()};r={'status':'SOURCE_ONLY_MDID494_FT495_35_RECORDS_MDIE_CONSUMERS_PENDING_GATES','schema':'openmitrastar.mdid494-ft495-source35/v1','hardware_accessed':False,'firmware_eligible':False,'parent':str(a.parent),'source_original_records':35,'qualified_combined_records':None,'existing_get495_faithful_EOPNOTSUPP_retained':True,'changed_sources':changes,'files':files,'old_comments_preserved':comments,'consumer_paths':['beaconconditionalIE54descriptor','APproberesponseconditionalIE54'],'VAP_fields':['u16om_mdid','u8om_ft_over_ds'],'limits':['OEM494HOSTAPlow16thenexistingbeaconcallback;495HOSTAPlow8withoutcallback. NoFTauth/DSmanagementhandlersrecovered.','Ownedframe5bytebudgetanddescriptoradmissioninheritedfullbeaconarena; new+1descriptorworstcaseauditrequired.','VAPtailgrowlikely4bytes+enclosingQdrvVAP fullallheaderusersrebuild/ABIprefixneeded.','NoRFclient/traffic/boot/persistence/recovery/releaseacceptance.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'source_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
