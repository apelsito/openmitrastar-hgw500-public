"""Bind the R8 setter-mode contract and reuse the complete R7 host unchanged."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,json,subprocess
import f367r8_campaign_worker as worker
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict

ROOT=worker.core.ROOT
def sha(path):return worker.baseline.sha(path)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def require(value,reason):worker.require(value,reason)

def bind_image(path,prior):
 q=read(path);require(q['schema']==worker.SCHEMA and q['status']==worker.STATUS,'r8_qualification')
 require(q['reproducible'] is True and q['bootbase']=='PASS' and q['slot_fit'] is True,'r8_offline_contract')
 image=Path(q['artifact']['path']).resolve();data=image.read_bytes();folder=image.parent;manifest=Path(q['manifest']);m=read(manifest)
 require(q['artifact']['sha256']==sha(image) and len(data)==q['artifact']['bytes'],'r8_exact_image');require(q['manifest_sha256']==sha(manifest),'r8_manifest')
 oldq=read(prior['candidate_qualification']['path']);campaign=q['campaign']
 for key,value in oldq['campaign'].items():
  if key not in ('runtime_revision','shell_runtime_reused_from'):require(campaign[key]==value,'reused_campaign_changed_'+key)
 require(campaign['runtime_revision']=='F367r8' and campaign['shell_runtime_reused_from']=='F367r7-except-controller','r8_lineage')
 refs=[campaign['mode_contract_test']]
 for ref in refs:require(sha(ref['path'])==ref['sha256'],'r8_delta_evidence_hash')
 delta=read(refs[0]['path']);require(delta['status'].startswith('PASS_') and delta['hardware_actions'] is False,'r8_mode_qualification')
 for source,digest in delta['source_pins'].items():require(sha(source)==digest,'mode_source_drift')
 allowed={'/etc/openmitrastar/release','/usr/sbin/om-f367-control','/usr/share/openmitrastar/dfs-f367/profile.json','/usr/share/openmitrastar/radio5g/artifacts.sha256','/usr/share/openmitrastar/storage/artifacts.sha256'}
 require(set(q['runtime_bindings'])==set(prior['runtime_bindings']),'r8_runtime_scope')
 for name,digest in prior['runtime_bindings'].items():
  if name not in allowed:require(q['runtime_bindings'][name]==digest,'reused_runtime_changed_'+name)
 require(q['runtime_bindings']['/usr/sbin/om-f367-control']!=prior['runtime_bindings']['/usr/sbin/om-f367-control'],'r8_control_not_changed')
 oldmanifest=read(Path(prior['images']['f367']['directory'])/'manifest.json')
 for key in ('kernel_lzma','dtb','config'):require(m['artifacts'][key]['sha256']==oldmanifest['artifacts'][key]['sha256'],'kernel_artifact_changed_'+key)
 old=prior['images']['f365'];require(all(q['recovery'][key]==old[key] for key in ('sha256','bytes','version','kernel_build')),'f365_fallback')
 store=Path(prior['store']['path']).read_bytes();require(hashlib.sha256(store).hexdigest()==prior['store']['sha256']==q['preserved_store']['sha256'],'store_hash')
 require(len(data)<worker.baseline.PREFIX,'slot_fit');prefix=data+b'\xff'*(worker.baseline.PREFIX-len(data));full=prefix+store
 require(image_to_dict(validate_bootbase_slot('f367r8',data,worker.baseline.SLOT))['accepted_by_contract'],'bootbase')
 require(worker.baseline.crc(full)==q['full_slot']['crc32'] and hashlib.sha256(full).hexdigest()==q['full_slot']['sha256'],'fullslot')
 known=folder/'known_hosts.f367';require(known.read_bytes()==Path(old['known_hosts_path']).read_bytes(),'ssh_identity')
 item=dict(directory=str(folder),base=image.name.removesuffix('.webformat.bin'),path=str(image),bytes=len(data),sha256=q['artifact']['sha256'],manifest_sha256=q['manifest_sha256'],version=q['product_version'],known_hosts='known_hosts.f367',known_hosts_path=str(known),kernel_build=old['kernel_build'],marker=old['marker'],crc32=worker.baseline.crc(data),prefix_crc32=worker.baseline.crc(prefix),full_slot_crc32=worker.baseline.crc(full),full_slot_sha256=hashlib.sha256(full).hexdigest(),preserved_store_sha256=prior['store']['sha256'],full_slot_scope='firmware prefix plus exact seq2 store')
 return q,item,m,refs,read(campaign['static_profile_qualification']['path'])

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--previous-plan',type=Path,required=True);p.add_argument('--completed-run',type=Path,required=True);p.add_argument('--candidate-result',type=Path,required=True);p.add_argument('--output-dir',type=Path);a=p.parse_args()
 prior=worker.previous.load_plan(a.previous_plan,sha(a.previous_plan));closed=read(a.completed_run)
 require(closed['status']=='FAIL_F367_WITH_F365_RETURN' and closed['error']=='control_failed_enter-dfs','previous_mode20_failure')
 require(closed['writer']['image']==prior['images']['f367']['sha256'] and closed['writer']['byte_compare'] is True,'previous_image_binding')
 require(closed['baseline_returned'] is True and closed['returned_identity']['boot_id']=='7046ec00-d1d5-432f-83d7-67c475d98d47','current_f365_boot')
 require(closed['restore_writer']['image']==prior['images']['f365']['sha256'] and closed['restore_writer']['byte_compare'] is True and closed['restore_writer']['full_slot_crc32']=='118901d4','current_f365_readback')
 require(closed['returned_store']['sha256']==prior['store']['sha256'] and closed['returned_configuration']['sequence']==2 and closed['returned_configuration']['active_sha256']==prior['boot_acceptance']['payload_sha256'],'current_store_config')
 require(closed['containment_confirmed'] is True and closed['retain_lease_required'] is False and closed['flash_command_in_flight'] is False and closed['watchdog_may_remain_armed'] is False,'previous_session_closed')
 require(closed['uart']['semantic_capture']['complete'] is True and closed['uart']['semantic_capture']['dropped_bytes']==0,'physical_capture_qualified')
 platform=Path(closed['return_platform']['result']);require(sha(platform)==closed['return_platform']['sha256'],'platform_hash');status=read(platform)
 require(status['status']=='PASS' and len(status['checks'])==27 and all(v is True for v in status['checks'].values()),'return_platform')
 q,image,manifest,refs,static=bind_image(a.candidate_result,prior)
 pins=dict(prior['sources']);files=[Path(__file__).resolve(),a.previous_plan.resolve(),a.completed_run.resolve(),a.candidate_result.resolve(),platform,Path(image['path']),Path(q['manifest']),Path(image['known_hosts_path']),Path(static['artifact']['path']),ROOT/'tools/f367r8_campaign_worker.py',ROOT/'tools/run_f367r8_campaign.py',ROOT/'tools/run_f367r8_campaign.ps1',*(Path(ref['path']) for ref in refs)]
 for source,digest in manifest['source']['inputs'].items():require(sha(source)==digest,'candidate_input_drift');files.append(Path(source).resolve())
 for source,digest in static['source_pins'].items():require(sha(source)==digest,'static_input_drift');files.append(Path(source).resolve())
 for ref in refs:
  for source,digest in read(ref['path'])['source_pins'].items():require(sha(source)==digest,'clock_capture_input_drift');files.append(Path(source))
 files.extend([ROOT/'tools/f367r7_clock_capture.py',ROOT/'tools/test_f367r7_clock_capture.py'])
 for file in files:pins[str(file.resolve())]=sha(file)
 require(worker.Host is worker.previous.Host,'r7_host_changed')
 require(all(sha(path)==digest for path,digest in pins.items()),'source_drift')
 out=(a.output_dir or ROOT/'outputs/preflight'/('f367r8-campaign-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve();require(not out.exists(),'immutable_output');out.mkdir(parents=True,exist_ok=False)
 plan=copy.deepcopy(prior);plan.update(runtime_revision='F367r8',repeat_scope='one-f367r8-mode-contract-trial',clock_observation_revision=7,
  images={'f367':image,'f365':prior['images']['f365']},runtime_bindings=q['runtime_bindings'],sources=pins,
  candidate_qualification=dict(path=str(a.candidate_result.resolve()),sha256=sha(a.candidate_result)),
  current_f365_return=dict(path=str(a.completed_run.resolve()),sha256=sha(a.completed_run),boot_id=closed['returned_identity']['boot_id']),
  mode_contract_test=refs[0],
  host_delta=dict(host_reused_from='F367r7',new_tests=0,previous_tests_rerun=False,qualified_banks_rerun=False,new_hardware_actions=False),
  changed_scope='Only control helper setter mode 11ac, readback remains11ac20 and safe diagnostics; kernel/modules/static helper/clocks/R7 host/V3/phase2/UART2/dispatcher and all horizons unchanged')
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=sha(path);worker.load_plan(path,digest)
 report=dict(status='PASS_OFFLINE_F367R8_CAMPAIGN_PLAN',plan=str(path),plan_sha256=digest,source_pins=len(pins),candidate_sha256=image['sha256'],full_slot_crc32=image['full_slot_crc32'],fallback_sha256=prior['images']['f365']['sha256'],hardware_actions=False,banks_rerun=False,new_tests=0)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='ascii');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
