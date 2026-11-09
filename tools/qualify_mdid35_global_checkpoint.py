"""Qualify SOURCE35r3 exactMDID/FTrecords withtypedfreshpair/control/residualpins."""
import argparse,hashlib,json
from pathlib import Path
from recover_hgw5g_driver_ops import Elf
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(path):
 s=str(path).replace('\\','/')
 if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
 return Path(s)if s.startswith('/')else ROOT/s
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--parent-checkpoint',type=Path,required=True);p.add_argument('--seed',type=Path,required=True);p.add_argument('--control',type=Path,required=True);p.add_argument('--pair',type=Path,required=True);p.add_argument('--source-checkpoint',type=Path,required=True);p.add_argument('--module-gate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);pins={};r={'status':'NO_GO_MDID35_R3_GLOBAL_CHECKPOINT','hardware_accessed':False,'firmware_eligible':False}
 def read(path):pins[str(path)]=sha(path);return json.loads(path.read_text())
 def pinmap(path):
  for x,d in read(path).items():x=norm(x);assert sha(x)==d,('pin',x);pins[str(x)]=d
 try:
  cp=read(a.candidate/'result.json');assert cp['source_original_records']==35 and cp['oem_probe_order']==['RRM','MDIE','AthAdvCaps']
  pp=read(a.parent_checkpoint/'result.json');assert pp['status']=='PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT'and pp['offline_original_records_reconstructed']==32
  pinmap(a.parent_checkpoint/'input-pins.json')
  sp=read(a.source_checkpoint/'result.json');assert sp['status']=='PASS_SOURCE_ONLY_MDID35_R3_OEM_ORDER_FULL_IE54_ADMISSION_TYPED_ABI_PENDING_MODULES';pinmap(a.source_checkpoint/'input-pins.json')
  seed=read(a.seed/'result.json');assert seed['status']=='PASS_MDID35_ALL58_HEADER_USERS_FRESH_TWO_WAVES_JOINT_MODULES_PENDING_GLOBAL'and seed['source_units_fresh']==116 and seed['reproducible'];pinmap(a.seed/'input-pins.json')
  control=read(a.control/'result.json');assert control['status']=='PASS_MDID35_MATCHED_HEADER_CONTROL32_PAIRED_MODULES_PENDING_GLOBAL'and control['fresh_compiles']==8 and control['same_header_exact_source_objects_reused']==108;pinmap(a.control/'input-pins.json')
  pair=read(a.pair/'result.json');assert pair['status']=='PASS_MDID35_MATCHED_HEADER_R3_PAIRED_MODULES_PENDING_GLOBAL'and pair['fresh_compiles']==2 and pair['same_header_exact_source_objects_reused']==114 and pair['reproducible'];pinmap(a.pair/'input-pins.json')
  for folder in[a.seed,a.control,a.pair]:
   for lane in['a','b']:
    j=folder/(lane+'-joint');jr=read(j/'result.json');assert jr['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'and jr['complete_modules']==7 and jr['modpost_diagnostics']=='empty';pinmap(j/'input-pins.json')
  mg=read(a.module_gate/'result.json');assert mg['status']=='PASS_MDID35_COMPLETE_MATCHED_HEADER_MODULE_RESIDUALS_AND_TWELVE_PARSED_NEGATIVES'and mg['negative_count']==12;pinmap(a.module_gate/'input-pins.json');assert all(v['status']in['PASS_COMPLETE_MDID35_R3_MATCHED_HEADER_RESIDUAL_SCOPE','BYTE_IDENTICAL_WHOLE_MATCHED_HEADER_CONTROL_MODULE']for v in mg['audits'].values())
  pm=norm(pp['modules'][0]['path']).parent.parent;parentrecords=Elf(pm/'wlan/wlan.ko').ioctl_records();records=Elf(a.pair/'a-joint/wlan/wlan.ko').ioctl_records();assert len(parentrecords)==598 and len(records)==601 and records[:598]==parentrecords
  added=[(x['cmd'],x['set_args'],x['get_args'],x['name'])for x in records[598:]];assert added==[(494,18433,0,'mdid'),(494,0,18433,'get_mdid'),(495,18433,0,'ft_over_ds')],added
  # AllunchangedparentCincluding449/461/491/492/493 exact outside4MDIEunits.
  changed=set()
  for path in(a.parent_source/'source').rglob('*'):
   if path.is_file():
    other=a.candidate/path.relative_to(a.parent_source);assert other.exists()
    if sha(path)!=sha(other):changed.add(str(path.relative_to(a.parent_source/'source')).replace('\\','/'))
  assert changed=={'wlan/ieee80211_wireless.c','wlan/ieee80211_beacon.c','wlan/ieee80211_beacon_desc.c','wlan/ieee80211_output.c'},changed
  for c in['qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth']:
   first=a.pair/'a-joint'/c/(c+'.ko');second=a.pair/'b-joint'/c/(c+'.ko');assert sha(first)==sha(second);pins[str(first)]=pins[str(second)]=sha(first)
  for path in[a.candidate/'mdid-ft-recovery.patch',Path(__file__),ROOT/'tools/test_mdid35_complete_module_gate.py',ROOT/'tools/build_mdid35_matched_variants.py',ROOT/'tools/build_mdid35_fresh_pair.py']:pins[str(path)]=sha(path)
  assert all(sha(path)==d for path,d in pins.items());(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'complete-module-audit.json').write_text(json.dumps(mg['audits'],indent=2)+'\n')
  r.update(status='PASS_OFFLINE_CONSOLIDATED35_R3_MDID_FT_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT',offline_original_records_reconstructed=35,remaining_original_records=9,private_table_records=601,faithful_unsupported_inherited=2,fullfunctional_driver_operations=None,modules=pair['modules'],full_newVAP_header_source_compiles=116,r3_changed_source_compiles=2,matched_header_control_compiles=8,exact_r3_seed_objects_reused=114,all_current_review_pins=len(pins),negative_cases=12,MDIE_byte_cases=sp['MDIE_cases'],control_caller_cases=sp['control_caller_cases'],probe_order_cases=sp['probe_order_cases'],IE54_admission_cases=sp['IE54_admission_cases'],old598_private_records_exact=True,old449_461_491_492_493_C_paths_preserved=True,complete_module_audits=mg['audits'],limits=['ExactOEM494setHOSTAPlow16existingbeaconupdate/getu16;495setHOSTAPlow8noimmediatecallback;existingget495faithfulEOPNOTSUPP.','IE54MDIEbeacon/probeconsumerbyteproducer/admissionandOEMprobeRRM-MDIE-Athorder qualifiedoffline. NoFTauth/roaming/key/frameexchangehandler recovered.','VAPsizeof+4/embeddedQDRVsize+4 all58usersfresh×2; control32Cwithsame35headers distinguisheslayoutfromfunctionaldeltas.','Changednamedfunctions are actualsourcefixturebound; fullresidualnamed/anonymouscode/data/symbol/RELA+negativechecks. NoOEMuniversal/lifetime/MuCtiming equivalence.','NoRF/clientAUTH/ASSOC/AUTHORIZED/traffic/soak/coldboot/persistence/rollback/recovery/releaseacceptance.'])
 except Exception as ex:r['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in r if k not in['modules','complete_module_audits']},indent=2));return int(not r['status'].startswith('PASS_'))
if __name__=='__main__':raise SystemExit(main())
