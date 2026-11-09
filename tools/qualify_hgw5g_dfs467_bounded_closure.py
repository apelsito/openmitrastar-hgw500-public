"""Bounded initialized-5GHz467 implementation/module proof, neverallmodesclaim."""
import argparse
import hashlib
import json
from pathlib import Path
from audit_hgw5g_dfs467_modules import audit
from qualify_f370_qdrv_module import Elf
from recover_hgw5g_driver_ops import Elf as OpsElf

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(p):
 s=str(p).replace('\\','/')
 if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
 return Path(s)if s.startswith('/')else ROOT/s

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--first',type=Path,required=True);p.add_argument('--second',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);pins={};result=dict(status='NO_GO_DFS467_BOUNDED_CLOSURE',hardware_accessed=False,firmware_eligible=False,allmode_oem467_recovery=False)
 try:
  def read(path):path=Path(path);raw=path.read_bytes();pins[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
  def import_pins(path):
   for p,h in read(path).items():p=norm(p);assert sha(p)==h,'input drift '+str(p);pins[str(p)]=h
  parent=ROOT/'outputs/rea/consolidated29-source-20261022T212500Z-r1';parentmods=ROOT/'outputs/rea/consolidated29-full-pair-20261022T214100Z-r2/a-joint';pq=read(ROOT/'outputs/rea/consolidated29-global-checkpoint-20261022T215400Z-r1/result.json');assert pq['status']=='PASS_OFFLINE_CONSOLIDATED29_RECORDS_SOURCE_MODULE_CHECKPOINT'
  b=read(a.build/'result.json');assert b['status']=='PASS_DFS467_SCAN_REVISION_PAIRED_SOURCE_CLOSURE'and b['new_input_compiles']==2 and b['retained_dfs467_changed_compiles']==4 and b['qualified_parent_whole_units_reused']==110;import_pins(a.build/'input-pins.json')
  mods=[read(d/'result.json')for d in(a.first,a.second)];assert all(r['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'and r['complete_modules']==7 and r['modpost_diagnostics']=='empty'for r in mods)
  for d in(a.first,a.second):import_pins(d/'input-pins.json')
  cp=read(a.candidate/'result.json');assert cp['candidate_private_record_added']==1 and not cp['host_layout_changed']
  for rel,h in cp['changed_sources'].items():path=a.candidate/rel;assert sha(path)==h;pins[str(path)]=h
  old=(parent/'headers/net80211/ieee80211_var.h').read_text();new=(a.candidate/'headers/net80211/ieee80211_var.h').read_text();assert new.replace('void ieee80211_pm_queue_work(struct ieee80211com *ic); int om_ieee80211_dfs_channel_available(struct ieee80211com *ic);','void ieee80211_pm_queue_work(struct ieee80211com *ic);')==old
  abi_dir=ROOT/'outputs/rea/dfs467-bounded-full-abi-20261022T224300Z-r1';abi=read(abi_dir/'result.json');assert abi['status']=='PASS_ARC_DFS467_ALL_OLD_FIELDS_WIRE_SIZES_UNCHANGED'and abi['host_delta']==0;import_pins(abi_dir/'input-pins.json');assert sha(a.candidate/'headers/net80211/ieee80211_var.h')==sha(ROOT/'outputs/rea/dfs467-bounded-source-20261022T224000Z-r1/headers/net80211/ieee80211_var.h')
  query_dir=ROOT/'outputs/rea/dfs467-bounded-actual-refresh-pick-20261022T225100Z-r3';query=read(query_dir/'result.json');assert query['status']=='PASS_ACTUAL_DFS467_QUERY_REFRESH_WHOLE_APSTART_AP_PICK_5GHZ_FIXTURE';import_pins(query_dir/'input-pins.json');getter_dir=ROOT/'outputs/rea/dfs467-bounded-getter-fixture-20261022T224500Z-r1';getter=read(getter_dir/'result.json');assert getter['status']=='PASS_ACTUAL_DFS467_WEXT_VALUE_RETURN_MASK_FIXTURE';import_pins(getter_dir/'input-pins.json')
  review=read(a.review);assert review['status'].startswith('PASS_')and not review['hardware_accessed']
  for row in review.get('evidence_pins',[]):path=norm(row['path']);assert sha(path)==row['sha256'];pins[str(path)]=row['sha256']
  for d in(query_dir,getter_dir):
   for f in d.iterdir():
    if f.is_file():pins[str(f)]=sha(f)
  neg_dir=ROOT/'outputs/rea/dfs467-bounded-negative-20261022T225500Z-r1';neg=read(neg_dir/'result.json');assert neg['status']=='PASS_TEN_DFS467_PARSED_NEGATIVE_DELTA_CASES'and neg['cases']==10;import_pins(neg_dir/'input-pins.json')
  reports={}
  for c in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
   op=parentmods/c/(c+'.ko');fp=a.first/c/(c+'.ko');sp=a.second/c/(c+'.ko');assert sha(fp)==sha(sp);pins[str(op)]=sha(op);pins[str(fp)]=pins[str(sp)]=sha(fp)
   if c in('wlan','wlan_scan_ap'):reports[c]=audit(Elf(op),Elf(fp),c)
   else:assert sha(op)==sha(fp);reports[c]=dict(status='BYTE_IDENTICAL_WHOLE_PARENT_MODULE',sha256=sha(fp))
  oldops=OpsElf(parentmods/'wlan/wlan.ko').ioctl_records();newops=OpsElf(a.first/'wlan/wlan.ko').ioctl_records();assert newops[:595]==oldops and[(r['cmd'],r['set_args'],r['get_args'],r['name'])for r in newops[595:]]==[(467,0,18433,'dfs_chan_avail')]
  for name in('windows-oem-dfs467-callback-20261022T223300Z-r2','windows-oem-dfs467-scanap-pick-20261022T223500Z-r1','windows-oem-dfs467-refresh-20261022T223500Z-r1'):
   d=ROOT/'outputs/rea'/name;r=read(d/'result.json');assert r['exit_code']==0 and r['target_unchanged'];pins[str(d/'rea.json')]=r['rea_output_sha256'];assert sha(d/'rea.json')==r['rea_output_sha256']
  for f in(Path(__file__),Path(__file__).with_name('audit_hgw5g_dfs467_modules.py'),Path(__file__).with_name('qualify_f370_qdrv_module.py'),Path(__file__).with_name('recover_hgw5g_driver_ops.py')):pins[str(f)]=sha(f)
  assert all(sha(p)==h for p,h in pins.items());(a.output/'complete-module-audit.json').write_text(json.dumps(reports,indent=2)+'\n');(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes());result.update(status='PASS_OFFLINE_DFS467_BOUNDED_5GHZ_INITIALIZED_SCANNER_MODULE_CLOSURE',bounded_record_added=1,allmode_qualified_records_unchanged=29,candidate_private_records=596,reproducible=True,new_scan_compiles=2,retained_dfs467_changed_compiles=4,qualified_parent_whole_units_reused=110,query_cases=query['cases'],missing_mode_cases=query['missing_mode_cases'],getter_cases=getter['cases'],old_field_abi=abi['old_members_checked'],negative_cases=10,pins_verified=len(pins),modules=mods[0]['modules'],limits=cp['limits']+cp['safety_deviations']+['20MHzdeterministicwholeAPstart/pickfixturewithfakecheck/alternatecallbacks; not40/80widthorallOEMmetric/rankingproof','Noallmode467acceptance orqualifiedfullrecordcountpromotion; noRF/PHY/regulatory/traffic/persistence/recovery/release'])
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
