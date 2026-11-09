"""Qualified32 retained plus one explicitbounded467extra; never33allmodeclaim."""
import argparse,hashlib,json
from pathlib import Path
from audit_consolidated32_bounded467_modules import audit
from qualify_f370_qdrv_module import Elf
from recover_hgw5g_driver_ops import Elf as OpsElf
from test_hgw5g_dfs467_refreshed_pick import extract
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(p):
 s=str(p).replace('\\','/')
 if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
 return Path(s)if s.startswith('/')else ROOT/s
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--pair',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);pins={};r=dict(status='NO_GO_CONSOLIDATED32_PLUS_BOUNDED467',hardware_accessed=False,firmware_eligible=False,allmode_oem467_recovery=False)
 try:
  def read(p):p=Path(p);pins[str(p)]=sha(p);return json.loads(p.read_text())
  def import_pins(p):
   for path,h in read(p).items():path=norm(path);assert sha(path)==h,'drift '+str(path);pins[str(path)]=h
  parent=ROOT/'outputs/rea/consolidated32-source-20261022T222600Z-r2';pm=ROOT/'outputs/rea/consolidated32-pair-20261022T223400Z-r2/a-joint';pc=ROOT/'outputs/rea/consolidated32-global-checkpoint-20261022T224200Z-r2';pq=read(pc/'result.json');assert pq['status']=='PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT'and pq['offline_original_records_reconstructed']==32;import_pins(pc/'input-pins.json')
  bounded=ROOT/'outputs/rea/dfs467-bounded-source-20261022T225000Z-r2';bq=ROOT/'outputs/rea/dfs467-bounded-qualification-20261022T225800Z-r2';br=read(bq/'result.json');assert br['status']=='PASS_OFFLINE_DFS467_BOUNDED_5GHZ_INITIALIZED_SCANNER_MODULE_CLOSURE'and not br['allmode_oem467_recovery'];import_pins(bq/'qualification-input-pins.json')
  cp=read(a.candidate/'result.json');assert cp['complete_original_records']==32 and cp['bounded_extra_records']==1 and cp['private_table_records']==599 and not cp['host_layout_changed']
  allowed={'headers/net80211/ieee80211_var.h','source/wlan/ieee80211_scan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c'};assert set(cp['changed_sources'])==allowed
  for f in('source','headers'):
   old={p.relative_to(parent).as_posix():sha(p)for p in(parent/f).rglob('*')if p.is_file()};new={p.relative_to(a.candidate).as_posix():sha(p)for p in(a.candidate/f).rglob('*')if p.is_file()};assert set(old)==set(new);assert {k for k in old if old[k]!=new[k]}==allowed.intersection(old)
   for rel,h in new.items():pins[str(a.candidate/rel)]=h
  rel='headers/net80211/ieee80211_var.h';old=(parent/rel).read_text();new=(a.candidate/rel).read_text();assert new.replace(' int om_ieee80211_dfs_channel_available(struct ieee80211com *ic);','')==old and len(old.splitlines())==len(new.splitlines())
  rel='source/wlan/ieee80211_scan.c';old=(parent/rel).read_text();new=(a.candidate/rel).read_text();bs=(bounded/rel).read_text();start=bs.index('/* OEM467:');end=bs.index('int ieee80211_get_type_of_neighborhood(',start);helper=bs[start:end];assert new.replace(helper,'',1)==old
  rel='source/wlan/ieee80211_scan_ap.c';old=(parent/rel).read_text();new=(a.candidate/rel).read_text();bs=(bounded/rel).read_text();start=bs.index('\t\t/* Exact OEM467 selector');end=bs.index('\t\t/* IEEE80211_SCAN_PICK_NOT_AVAILABLE_DFS_ONLY',start);assert new.replace(bs[start:end],'',1)==old
  rel='source/wlan/ieee80211_wireless.c';old=(parent/rel).read_text();new=(a.candidate/rel).read_text();new=new.replace('#define OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE 467\n','',1);new=new.replace('\n\tcase OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE:\n\t\tparam[0]=om_ieee80211_dfs_channel_available(ic);\n\t\treturn 0;\n','',1);new=new.replace('\n\t{ OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE,0,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,"dfs_chan_avail" },','',1);assert new==old
  build=read(a.pair/'result.json');assert build['status']=='PASS_CONSOLIDATED32_BOUNDED467_THREE_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL'and build['new_compiled_units']==6 and build['exact_parent32_objects_reused']==110 and build['reproducible'];import_pins(a.pair/'input-pins.json')
  mods=[]
  for lane in('a','b'):
   d=a.pair/(lane+'-joint');v=read(d/'result.json');assert v['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'and v['complete_modules']==7 and v['modpost_diagnostics']=='empty';import_pins(d/'input-pins.json');mods.append(v)
  receipts={}
  for name,status in [('query','PASS_ACTUAL_CONSOLIDATED32_BOUNDED467_WHOLE_APSTART_PICK_WITH_REAL461_PREDICATES'),('getter','PASS_ACTUAL_DFS467_WEXT_VALUE_RETURN_MASK_FIXTURE'),('full-abi','PASS_ARC_DFS467_ALL_OLD_FIELDS_WIRE_SIZES_UNCHANGED'),('policy461','PASS_CONSOLIDATED32_ACTUAL_461_WEXT_SCANNER_POLICY_FIXTURE'),('negative','PASS_TEN_DFS467_PARSED_NEGATIVE_DELTA_CASES')]:
   dates={'query':'231300','getter':'231300','full-abi':'231400','policy461':'231700','negative':'231900'};d=ROOT/('outputs/rea/consolidated32-plus-bounded467-'+name+'-20261022T'+dates[name]+'Z-r1');v=read(d/'result.json');assert v['status']==status
   if(d/'input-pins.json').exists():import_pins(d/'input-pins.json')
   for path,h in v.get('pins',{}).items():path=norm(path);assert sha(path)==h;pins[str(path)]=h
   for path in d.iterdir():
    if path.is_file():pins[str(path)]=sha(path)
   receipts[name]=v
  assert receipts['query']['cases']==28672 and receipts['getter']['cases']==131072 and receipts['policy461']['cases']==262144 and receipts['negative']['cases']==10 and receipts['full-abi']['host_delta']==0
  reports={}
  for c in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
   op=pm/c/(c+'.ko');fp=a.pair/'a-joint'/c/(c+'.ko');sp=a.pair/'b-joint'/c/(c+'.ko');assert sha(fp)==sha(sp);pins[str(op)]=sha(op);pins[str(fp)]=pins[str(sp)]=sha(fp)
   if c in('wlan','wlan_scan_ap'):reports[c]=audit(Elf(op),Elf(fp),c)
   else:assert sha(op)==sha(fp);reports[c]=dict(status='BYTE_IDENTICAL_WHOLE_PARENT32_MODULE',sha256=sha(fp))
  old=OpsElf(pm/'wlan/wlan.ko').ioctl_records();new=OpsElf(a.pair/'a-joint/wlan/wlan.ko').ioctl_records();assert len(old)==598 and new[:598]==old and [(r['cmd'],r['set_args'],r['get_args'],r['name'])for r in new[598:]]==[(467,0,18433,'dfs_chan_avail')]
  for path in[Path(__file__),Path(__file__).with_name('audit_consolidated32_bounded467_modules.py'),Path(__file__).with_name('prepare_consolidated32_bounded467.py')]:pins[str(path)]=sha(path)
  assert all(sha(p)==h for p,h in pins.items());(a.output/'complete-module-audit.json').write_text(json.dumps(reports,indent=2)+'\n');(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes());r.update(status='PASS_OFFLINE_CONSOLIDATED32_PLUS_ONE_BOUNDED467_SEVEN_MODULE_CHECKPOINT',complete_original_records=32,remaining_complete_original_records=12,bounded_extra_records=1,private_table_records=599,reproducible=True,all_461_source_hooks_preserved=True,old_private_records_exact=598,fresh_source_compiles=6,parent32_whole_objects_reused=110,modules=mods[0]['modules'],query_cases=28672,missing_query_cases=96,getter_cases=131072,policy461_cases=262144,all_old_members_checked=receipts['full-abi']['old_members_checked'],negative_cases=10,current_pins_verified=len(pins),inherited_limits=pq['limits'],bounded_limits=cp['limits']+cp['safety_deviations']+['Stable20MHzactualAP/querywithfakechannelcheck/alternatecallbacks;no40/80/allmetric/rankingproof','ANYCnonemptylistfallbackcanstillreturnnonDFS;neveruniversalDFSavailabilityclaim','Nooverlapscan/hotdetachlivequeryserializationproof','NoRF/client/traffic/coldboot/persistence/rollback/releaseacceptance'])
 except Exception as ex:r['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return int(not r['status'].startswith('PASS_'))
if __name__=='__main__':raise SystemExit(main())
