"""Bind exact F367r3 using immutable prior qualification; no hardware/builds."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,json,subprocess,sys
import f367r3_campaign_worker as worker
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict

ROOT=worker.core.ROOT
def sha(path):return worker.baseline.sha(path)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def require(value,reason):worker.require(value,reason)

def bind_image(path,prior):
 q=read(path);require(q['schema']=='openmitrastar.f367r3-owned-lock-image/v1' and q['status']=='PASS_OFFLINE_F367R3_OWNED_LOCK_IMAGE','r3_qualification')
 require(q['reproducible'] is True and q['bootbase']=='PASS' and q['slot_fit'] is True,'r3_offline_contract')
 image=Path(q['artifact']['path']).resolve();data=image.read_bytes();folder=image.parent;manifest=folder/'manifest.json'
 require(q['artifact']['sha256']==worker.IMAGE_SHA==sha(image) and len(data)==q['artifact']['bytes']==5459968,'r3_exact_image')
 require(q['manifest_sha256']==sha(manifest),'r3_manifest')
 campaign=q['campaign'];expected=dict(runtime_revision='F367r3',preamble_phase_ms=30000,module_load_phase_ms=30000,foreground_preamble_health=True,keeper_ack_required_before_module_load=True,lock_cleanup_failure_exit=74)
 require(all(campaign.get(k)==v for k,v in expected.items()),'protected_preamble_lock_scope')
 require(campaign['startup_phases']==['preamble','module-load','core-start','vap-create','radio-nondfs','native-radar'],'startup_phase_order')
 for k,v in dict(callback_authority=1,bootstrap_channel=36,bootstrap_bandwidth=80,dfs_channel=52,dfs_bandwidth=20,escape_channel=36,quarantine_ms=1800000,cac_ms=70000,nop_ms=1800000,supervisor_total_ms=5400000).items():require(campaign[k]==v,'unchanged_'+k)
 old=prior['images']['f365'];recovery=q['recovery']
 require(all(recovery[k]==old[k] for k in ('sha256','bytes','version','kernel_build')),'f365_fallback')
 store=Path(prior['store']['path']).read_bytes();require(hashlib.sha256(store).hexdigest()==prior['store']['sha256'],'store_hash')
 require(len(data)<worker.baseline.PREFIX,'slot_fit')
 prefix=data+b'\xff'*(worker.baseline.PREFIX-len(data));full=prefix+store
 contract=image_to_dict(validate_bootbase_slot('f367r3',data,worker.baseline.SLOT));require(contract['accepted_by_contract'],'bootbase')
 require(worker.baseline.crc(full)==q['full_slot']['crc32']=='3def6860' and hashlib.sha256(full).hexdigest()==q['full_slot']['sha256'],'fullslot')
 known=folder/'known_hosts.f367';require(known.read_bytes()==Path(old['known_hosts_path']).read_bytes(),'ssh_identity')
 for name,digest in prior['runtime_bindings'].items():
  if name.endswith('.ko') or name in ('/usr/sbin/om-radar-engine-f367','/usr/sbin/om-watchdog-supervisor-f367'):
   require(q['runtime_bindings'][name]==digest,'binary_changed_'+name)
 refs=[campaign['lock_release_delta_test'],campaign['lock_release_target_probe']]
 for ref in refs:require(sha(ref['path'])==ref['sha256'],'lock_evidence_hash')
 delta=read(refs[0]['path']);probe=read(refs[1]['path'])
 require(delta['status']=='PASS_OWNED_LOCK_RELEASE_REAL_IPC_WITHOUT_RMDIR' and len(delta['checks'])==8 and delta['path_has_rmdir'] is False,'lock_delta')
 require(probe['status']=='PASS' and probe['host']=='192.168.1.90' and probe['exit_code']==0 and probe['radio_or_mtd_actions'] is False,'target_lock_probe')
 item=dict(directory=str(folder),base=image.name.removesuffix('.webformat.bin'),path=str(image),bytes=len(data),sha256=q['artifact']['sha256'],manifest_sha256=q['manifest_sha256'],version=q['product_version'],known_hosts='known_hosts.f367',known_hosts_path=str(known),kernel_build=old['kernel_build'],marker=old['marker'],crc32=worker.baseline.crc(data),prefix_crc32=worker.baseline.crc(prefix),full_slot_crc32=worker.baseline.crc(full),full_slot_sha256=hashlib.sha256(full).hexdigest(),preserved_store_sha256=prior['store']['sha256'],full_slot_scope='firmware prefix plus exact seq2 store')
 return q,item,read(manifest),refs

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--previous-plan',type=Path,required=True);p.add_argument('--completed-run',type=Path,required=True);p.add_argument('--candidate-result',type=Path,required=True);p.add_argument('--output-dir',type=Path);a=p.parse_args()
 prior=worker.core.load_plan(a.previous_plan,sha(a.previous_plan));closed=read(a.completed_run)
 require(closed['status']=='FAIL_F367_WITH_F365_RETURN' and closed['error']=='control_timeout_activate','closed_previous_failure')
 require(closed['baseline_returned'] is True and closed['returned_identity']['boot_id']=='86c21b2b-91ac-4c48-84fd-48d387083b42','current_f365_boot')
 require(closed['restore_writer']['image']==prior['images']['f365']['sha256'] and closed['restore_writer']['byte_compare'] is True and closed['restore_writer']['full_slot_crc32']=='118901d4','current_f365_readback')
 require(closed['returned_store']['sha256']==prior['store']['sha256'] and closed['returned_configuration']['sequence']==2 and closed['returned_configuration']['active_sha256']==prior['boot_acceptance']['payload_sha256'],'current_store_config')
 require(closed['containment_confirmed'] is True and closed['retain_lease_required'] is False and closed['flash_command_in_flight'] is False and closed['watchdog_may_remain_armed'] is False,'previous_session_closed')
 require(closed['uart']['semantic_capture']['complete'] is True and closed['uart']['semantic_capture']['dropped_bytes']==0,'physical_capture_qualified')
 platform=Path(closed['return_platform']['result']);require(sha(platform)==closed['return_platform']['sha256'],'platform_hash')
 status=read(platform);require(status['status']=='PASS' and len(status['checks'])==27 and all(v is True for v in status['checks'].values()),'return_platform')
 q,image,manifest,refs=bind_image(a.candidate_result,prior)
 pins=dict(prior['sources'])
 files=[Path(__file__).resolve(),a.previous_plan.resolve(),a.completed_run.resolve(),a.candidate_result.resolve(),platform,Path(image['path']),Path(image['directory'])/'manifest.json',Path(image['known_hosts_path']),ROOT/'tools/f367r3_campaign_worker.py',ROOT/'tools/run_f367r3_campaign.py',ROOT/'tools/run_f367r3_campaign.ps1',ROOT/'tools/test_f367r3_host_binding.py',*(Path(ref['path']) for ref in refs)]
 for source,digest in manifest['source']['inputs'].items():require(sha(source)==digest,'candidate_input_drift');files.append(Path(source).resolve())
 for file in files:pins[str(file.resolve())]=sha(file)
 out=(a.output_dir or ROOT/'outputs/preflight'/('f367r3-campaign-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve();require(not out.exists(),'immutable_output');out.mkdir(parents=True,exist_ok=False)
 test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tools','-p','test_f367r3_host_binding.py','-v'],cwd=ROOT,capture_output=True,timeout=30)
 (out/'binding.stdout').write_bytes(test.stdout);(out/'binding.stderr').write_bytes(test.stderr);require(test.returncode==0,'host_binding_delta')
 require(all(sha(path)==digest for path,digest in pins.items()),'source_drift')
 plan=copy.deepcopy(prior);plan.update(runtime_revision='F367r3',activate_timeout_seconds=240,uart_semantic_capture_revision=2,repeat_scope='one-f367r3-owned-lock-trial',max_completed_executions=1,
  images={'f367':image,'f365':prior['images']['f365']},runtime_bindings=q['runtime_bindings'],sources=pins,
  candidate_qualification=dict(path=str(a.candidate_result.resolve()),sha256=sha(a.candidate_result)),
  current_f365_return=dict(path=str(a.completed_run.resolve()),sha256=sha(a.completed_run),boot_id=closed['returned_identity']['boot_id']),
  protected_preamble=dict(budget_ms=30000,module_load_budget_ms=30000,keeper_ack_required=True,health_lease_ms=5000),
  lock_release_qualification=refs,host_delta=dict(activate_timeout_seconds=240,other_control_timeout_seconds=30,new_tests=1,firmware_or_supervisor_rebuilt=False,qualified_banks_rerun=False),
  changed_scope='Protected shell preamble and owned lock release; unchanged binary radar/watchdog/CAC/NOP; full UART capture retained')
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=sha(path);worker.load_plan(path,digest)
 result=dict(status='PASS_OFFLINE_F367R3_CAMPAIGN_PLAN',plan=str(path),plan_sha256=digest,source_pins=len(pins),candidate_sha256=image['sha256'],full_slot_crc32=image['full_slot_crc32'],fallback_sha256=prior['images']['f365']['sha256'],hardware_actions=False,banks_rerun=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii');print(json.dumps(result,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
