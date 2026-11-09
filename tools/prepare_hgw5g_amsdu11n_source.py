"""Prepareexact typedVAP484 setter/getter and actualADDBA consumer, source only.

Appendonlyu8 iv_tx_amsdu_11n distinct from iv_tx_amsdu. OEMVAPsetup default1,
changedboolsetter→SETPARAM11/76B payload id484→MuCnode+80+reassoc; getterfield.
ADDBApredicate matchesOEMHT/nonVHT condition. Noaggregation/performance/RFclaim.
EveryVAP/headerconsumermustrebuild andABI/delta/module gatespass beforepromotion.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


ROOT=Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--setup-evidence',type=Path,required=True);p.add_argument('--tx-evidence',type=Path,required=True);p.add_argument('--muc-evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 parent=json.loads((a.parent/'result.json').read_text());assert parent['entries_total_added']==18
 setup=json.loads(a.setup_evidence.read_text());tx=json.loads(a.tx_evidence.read_text());muc=json.loads(a.muc_evidence.read_text());assert setup['ok']and tx['ok']and muc['ok']
 s=setup['data']['raw_result']['value']['pseudocode'];t=tx['data']['raw_result']['value']['pseudocode'];m=muc['data']['raw_result']['value']['pseudocode']
 assert'(param_2 + 0xf55) = 1' in s and'(param_2 + 0xf54) = 1'in s
 assert'0xc54'in t and'0xc55'in t and'0x4008'in t and'0x80'in m and'0x4000'in m
 a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');qdrv=a.output/'source/qdrv';wlan=a.output/'source/wlan'
 base=ROOT/'work/linux510-radio-port/quantenna/wlan'
 for path in base.iterdir():
  if path.is_file()and path.suffix in('.c','.h')and not path.name.endswith('.mod.c'):
   destination=wlan/path.name
   if not destination.exists():shutil.copyfile(path,destination)
 shutil.copyfile(a.parent/'ieee80211_wireless.c',wlan/'ieee80211_wireless.c')
 headerbase=ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_var.h';oldheader=headerbase.read_text();header=a.output/'headers/net80211/ieee80211_var.h';header.parent.mkdir(parents=True)
 marker='\tuint8_t\t\t\tiv_11ac_and_11n_flag;\t/* 1 - IEEE80211_AC_ONLY, 2 - IEEE80211_N_ONLY */\n};';assert oldheader.count(marker)==1
 append='\t/* OEM484distinctVAP11n A-MSDUpolicy; noexistingmemberoffset changes. */\n\tu8 iv_tx_amsdu_11n;\n'
 header.write_text(oldheader.replace(marker,marker.replace('\n};','\n'+append+'};'),1),newline='\n')
 originals={};patches=[]
 for name in('ieee80211_wireless.c','ieee80211.c','ieee80211_output.c'):
  path=wlan/name;old=path.read_text();originals[name]=old;new=old
  if name=='ieee80211_wireless.c':
   new=new.replace('#define OM_OEM_PARAM_DEVICE_MODE 451','#define OM_OEM_PARAM_TX_AMSDU_11N 484\n#define OM_OEM_PARAM_DEVICE_MODE 451',1)
   start=new.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param)',start))
   block='''
\tcase OM_OEM_PARAM_TX_AMSDU_11N:
\t\t/* ExactOEMchangedboolpath; fulloriginalvalue reachesMuCparam484. */
\t\tif (vap->iv_tx_amsdu_11n != !!value) {
\t\t\tvap->iv_tx_amsdu_11n = !!value;
\t\t\tieee80211_param_to_qdrv(vap, param, value, NULL, 0);
\t\t\tieee80211_wireless_reassoc(vap, 0, 1);
\t\t}
\t\tbreak;
''';new=new[:brace+1]+block+new[brace+1:]
   start=new.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param[0] & 0xffff)',start));block='\n\tcase OM_OEM_PARAM_TX_AMSDU_11N:\n\t\tparam[0] = vap->iv_tx_amsdu_11n;\n\t\tbreak;\n';new=new[:brace+1]+block+new[brace+1:]
   start=new.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new.index('\n};',start);entries='\n\t{ OM_OEM_PARAM_TX_AMSDU_11N,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "txamsdu_11n" },\n\t{ OM_OEM_PARAM_TX_AMSDU_11N,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_txamsdu_11n" },';new=new[:end]+entries+new[end:]
  elif name=='ieee80211.c':
   marker='\tvap->iv_tx_amsdu = 1;';assert new.count(marker)==1;new=new.replace(marker,marker+'\n\tvap->iv_tx_amsdu_11n = 1; /* exactOEM484VAPsetupdefault */',1)
  else:
   marker='\t\t\t\tif (vap->iv_tx_amsdu)\n\t\t\t\t\ttemp16 |= IEEE80211_A_BA_AMSDU_SUPPORTED;';assert new.count(marker)==1
   replacement='''\t\t\t\tif (vap->iv_tx_amsdu &&
\t\t\t\t    (((ni->ni_flags & (IEEE80211_NODE_HT | IEEE80211_NODE_VHT))
\t\t\t\t       != IEEE80211_NODE_HT) || vap->iv_tx_amsdu_11n))
\t\t\t\t\ttemp16 |= IEEE80211_A_BA_AMSDU_SUPPORTED;''';new=new.replace(marker,replacement,1)
  path.write_text(new,newline='\n');patches.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/src/wlan/'+name,tofile='b/src/wlan/'+name)))
 patches.append(''.join(difflib.unified_diff(oldheader.splitlines(True),header.read_text().splitlines(True),fromfile='a/vendor/port-context/drivers/include/kernel/net80211/ieee80211_var.h',tofile='b/vendor/port-context/drivers/include/kernel/net80211/ieee80211_var.h')))
 (a.output/'amsdu11n-recovery.patch').write_text(''.join(patches),newline='\n')
 result=dict(status='SOURCE_ONLY_TYPED_VAP_AMSDU11N_20_ENTRIES_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,parent_manifest_sha256=sha(a.parent/'result.json'),total_original_entries_added=20,functional_ops_source=18,faithful_unsupported=2,remaining_original_table_gaps=24,changed_wlan_sources={n:sha(wlan/n)for n in originals},header_sha256=sha(header),existing_qdrv_sha256=sha(qdrv/'qdrv_wlan.c'),wire_contract='ExistingSETPARAM11/76Bpayload id484, originalintvalue forwarded; MuCnode+0x80',typed_field='struct ieee80211vap.iv_tx_amsdu_11n:u8 appended',default=1,owned_by='VAPallocation/setup/teardown,noextraresource',provenance={str(p):sha(p)for p in(a.setup_evidence,a.tx_evidence,a.muc_evidence)},constraints=['EveryQDRV/WLAN/scan/crypto/otherVAPheaderuserneedsfullrebuild','ARCprefixoffsets unchanged butstructqdrv_vapafterembedding shifts; fullmoduleclosuremandatory','ADDBApeercontext usesactualni_flags, nosurrogateBSSgetter','Noaggregateperformance/client/RFacceptanceclaim'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
