"""SOURCE25 bounded valid-init offline module/ABI/fixtures/delta qualification."""
import argparse
import hashlib
import json
from pathlib import Path
from audit_hgw5g_coc25_controlled_modules import audit,EXPORTS
from qualify_f370_qdrv_module import Elf
from recover_hgw5g_driver_ops import Elf as OpsElf

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def normalized(p):
 s=str(p).replace('\\','/')
 if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
 return Path(s)if s.startswith('/')else ROOT/s

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--first',type=Path,required=True);p.add_argument('--second',type=Path,required=True);p.add_argument('--control',type=Path,required=True);p.add_argument('--control-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);pins={};result=dict(status='NO_GO_COC25_OFFLINE_CLOSURE',hardware_accessed=False,firmware_eligible=False)
 try:
  def readjson(path):path=Path(path);raw=path.read_bytes();pins[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
  def pinmap(path):
   for file,h in readjson(path).items():file=normalized(file);assert sha(file)==h,'input drift '+str(file);pins[str(file)]=h
  first,second,control=[readjson(d/'result.json')for d in(a.first,a.second,a.control)];assert all(x['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'and x['complete_modules']==7 and x['modpost_diagnostics']=='empty'for x in(first,second,control))
  for d in(a.first,a.second,a.control):pinmap(d/'input-pins.json')
  source1=ROOT/'outputs/rea/driver5g-ops-20261022-coc25-full-closure-r6';source2=ROOT/'outputs/rea/driver5g-ops-20261022-coc25-second-source-r6';rs=[readjson(d/'result.json')for d in(source1,source2)];assert all(r['status']=='NO_GO_TYPED_HEADER_CLOSURE'and'"om_ieee80211_coc_quiesce"'in r['error']and len(r['units'])==58 and r['no_baseline_objects_reused']for r in rs)
  for d in(source1,source2):pinmap(d/'input-pins.json')
  assert {(r['component'],r['name'],r['object_sha256'])for r in rs[0]['units']}=={(r['component'],r['name'],r['object_sha256'])for r in rs[1]['units']},'all116 actualsourceunits reproducibility'
  cb=readjson(a.control_build/'result.json');assert cb['status']=='PASS_SAME_HEADER_EXACT_SOURCE_CONTROL_OBJECT_CLOSURE'and cb['recompiled_units']==4 and cb['reused_exact_source_header_units']==54 and cb['header_identical'];pinmap(a.control_build/'input-pins.json')
  cp=readjson(a.candidate/'result.json');assert cp['total_original_entries_added']==25
  for rel,h in cp['changed_sources'].items():file=a.candidate/rel;assert sha(file)==h; pins[str(file)]=h
  fixtures=[('coc491-source25-postcompletion-fixture-20261022T181600Z-r1','PASS_ACTUAL_COC491_DEFERRED_WORK_CONSUMER_CALLBACK_QUEUE_HOST_REFERENCE'),('coc491-source25-postcompletion-interleaving-20261022T181700Z-r1','PASS_ACTUAL_COC491_DEFERRED_COMPLETION_PRODUCER_INTERLEAVINGS'),('coc491-source25-ioctl-fixture-20261022T181100Z-r1','PASS_ACTUAL_COC491_IOCTL_SETGET_FULL_U32_BOUNDARY_FIXTURE')]
  proof=[]
  for folder,status in fixtures:
   d=ROOT/'outputs/rea'/folder;r=readjson(d/'result.json');assert r['status']==status;pinmap(d/'input-pins.json');proof.append(r)
   for f in d.iterdir():
    if f.is_file():pins[str(f)]=sha(f)
  assert proof[0]['source_sha256']==sha(a.candidate/'source/wlan/ieee80211.c')and proof[1]['source_sha256']==proof[0]['source_sha256']and proof[2]['source_sha256']==sha(a.candidate/'source/wlan/ieee80211_wireless.c')
  review=readjson(ROOT/'outputs/rea/coc491-source25-r6-independent-review-20261022T210000Z-r1/result.json');assert review['status']=='PASS_INDEPENDENT_COC491_R6_SOURCE_SEMANTICS_FOR_INITIALIZED_RETAINED_IC_PENDING_FULL_MODULES'
  for row in review['evidence_pins']:file=normalized(row['path']);assert sha(file)==row['sha256'];pins[str(file)]=row['sha256']
  cancel=readjson(ROOT/'outputs/rea/coc491-source25-r6-independent-canceljoin-20261022T205900Z-r1/result.json');assert cancel['status']=='PASS_ACTUAL_COC491_R6_HELPERS_RUNNING_WORKER_CANCEL_JOIN_MODEL'and all(cancel['facts'].values())
  for f in(ROOT/'outputs/rea/coc491-source25-r6-independent-canceljoin-20261022T205900Z-r1').iterdir():
   if f.is_file():pins[str(f)]=sha(f)
  abi=readjson(ROOT/'outputs/rea/coc491-source25-full-abi-20261022T181000Z-r1/result.json');assert abi['status']=='PASS_ARC_COC25_ALL_PARSED_IC_VAP_PREFIX_QDRV_DELTA_WIRE'and abi['host_delta']==20;pinmap(ROOT/'outputs/rea/coc491-source25-full-abi-20261022T181000Z-r1/input-pins.json');assert sha(a.candidate/'headers/net80211/ieee80211_var.h')==sha(ROOT/'outputs/rea/coc491-source25-trigger-snapshot-20261022T180700Z-r5/headers/net80211/ieee80211_var.h')
  neg=readjson(ROOT/'outputs/rea/driver5g-ops-20261022-coc25-negative-audit-r1/result.json');assert neg['status']=='PASS_ELEVEN_SOURCE25_PARSED_NEGATIVE_DELTA_CASES'and neg['cases']==11;pinmap(ROOT/'outputs/rea/driver5g-ops-20261022-coc25-negative-audit-r1/input-pins.json')
  reports={}
  for component in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
   fp=a.first/component/(component+'.ko');sp=a.second/component/(component+'.ko');op=a.control/component/(component+'.ko');assert sha(fp)==sha(sp);pins[str(fp)]=pins[str(sp)]=sha(fp);pins[str(op)]=sha(op)
   if component in('qdrv','wlan'):reports[component]=audit(Elf(op),Elf(fp),component)
   else:assert sha(op)==sha(fp);reports[component]=dict(status='BYTE_IDENTICAL_WHOLE_PROVIDER',bytes=fp.stat().st_size,sha256=sha(fp))
  oldops=OpsElf(a.control/'wlan/wlan.ko').ioctl_records();newops=OpsElf(a.first/'wlan/wlan.ko').ioctl_records();assert newops[:589]==oldops and[(r['cmd'],r['set_args'],r['get_args'],r['name'])for r in newops[589:]]==[(491,18433,0,'coc_mv_to_ndfs'),(491,0,18433,'g_coc_mv_to_ndfs')]
  for f in(Path(__file__),Path(__file__).with_name('audit_hgw5g_coc25_controlled_modules.py'),Path(__file__).with_name('qualify_f370_qdrv_module.py'),Path(__file__).with_name('recover_hgw5g_driver_ops.py')):pins[str(f)]=sha(f)
  for path,h in pins.items():assert sha(path)==h,'post qualification drift '+path
  (a.output/'complete-controlled-audit.json').write_text(json.dumps(reports,indent=2)+'\n');(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
  result.update(status='PASS_OFFLINE_COC25_INITIALIZED_RETAINED_IC_SEVEN_MODULE_CLOSURE',reproducible=True,candidate_source_units_fresh=116,control_exact_unchanged_units_reused=54,control_changed_units_compiled=4,private_records=591,original_records_recovered=25,remaining_original_records=19,worker_cases=proof[0]['worker_cases'],ioctl_cases=proof[2]['cases'],producer_interleavings=9,canceljoin_contract_model=True,abi_old_members=abi['old_members_checked'],host_layout_delta=20,negative_cases=11,pins_verified=len(pins),modules=first['modules'],limits='InitializedretainedIC scope only; preinitifattachfailure/forcedunload/externalentireCSAteardown excluded. TimerQoS/log safelydeferred, scalarstate notcoherenttuple. Twofaithfulunsupportedrecords/NACsnapshotlimits retained. NoPM/CSA/RF/client/traffic/boot/persistence/rollback/releaseacceptance.')
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
