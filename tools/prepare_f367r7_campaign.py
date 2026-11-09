"""Bind R7 clock publication and its narrow host capture without rerunning banks."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,json,subprocess
import f367r7_campaign_worker as worker
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict

ROOT=worker.core.ROOT
def sha(path):return worker.baseline.sha(path)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def require(value,reason):worker.require(value,reason)

def bind_image(path,prior):
 q=read(path);require(q['schema']==worker.SCHEMA and q['status']==worker.STATUS,'r7_qualification')
 require(q['reproducible'] is True and q['bootbase']=='PASS' and q['slot_fit'] is True,'r7_offline_contract')
 image=Path(q['artifact']['path']).resolve();data=image.read_bytes();folder=image.parent;manifest=Path(q['manifest']);m=read(manifest)
 require(q['artifact']['sha256']==sha(image) and len(data)==q['artifact']['bytes'],'r7_exact_image');require(q['manifest_sha256']==sha(manifest),'r7_manifest')
 oldq=read(prior['candidate_qualification']['path']);campaign=q['campaign']
 for key,value in oldq['campaign'].items():
  if key not in ('runtime_revision','shell_runtime_reused_from'):require(campaign[key]==value,'reused_campaign_changed_'+key)
 require(campaign['runtime_revision']=='F367r7' and campaign['shell_runtime_reused_from'] in (oldq['campaign']['shell_runtime_reused_from'],'F367r6'),'r7_lineage')
 local=ROOT/'outputs/preflight/f367r7-clock-capture-20260922T193902Z/result.json'
 refs=[campaign['clock_observation_test'],campaign['clock_json_test'],dict(path=str(local),sha256=sha(local))]
 for ref in refs:require(sha(ref['path'])==ref['sha256'],'r7_delta_evidence_hash')
 clock,capacity,host=(read(ref['path']) for ref in refs)
 require(clock['status']=='PASS_F367R7_DUAL_CLOCK_PUBLICATION' and 'checks=28 ' in clock['host_output'] and clock['deadline_producers_unchanged'] is True and clock['physical_tick_loss_measured'] is False,'r7_clock_publication')
 require(capacity['status']=='PASS_MAX_CLOCK_JSON_BELOW_PAGE_SIZE' and capacity['bytes']<capacity['page_size']==4096 and capacity['canaries_unchanged'] is True,'r7_json_capacity')
 require(host['status']=='PASS_HOST_CLOCK_CAPTURE_DELTA' and host['tests']==2 and host['exit_code']==0,'r7_host_capture_delta')
 for evidence in (clock,capacity,host):
  for source,digest in evidence['source_pins'].items():require(sha(source)==digest,'clock_source_drift')
 native='/usr/libexec/openmitrastar/om-radio5-start-f367-native';qdrv=next(name for name in prior['runtime_bindings'] if name.endswith('/qdrv.ko'))
 allowed={'/etc/openmitrastar/release',qdrv,native,'/usr/share/openmitrastar/dfs-f367/profile.json','/usr/share/openmitrastar/radio5g/artifacts.sha256','/usr/share/openmitrastar/radio5g/driver-contract.env','/usr/share/openmitrastar/storage/artifacts.sha256'}
 require(set(q['runtime_bindings'])==set(prior['runtime_bindings']),'r7_runtime_scope')
 for name,digest in prior['runtime_bindings'].items():
  if name not in allowed:require(q['runtime_bindings'][name]==digest,'reused_runtime_changed_'+name)
 oldmanifest=read(Path(prior['images']['f367']['directory'])/'manifest.json')
 for key in ('kernel_lzma','dtb','config'):require(m['artifacts'][key]['sha256']==oldmanifest['artifacts'][key]['sha256'],'kernel_artifact_changed_'+key)
 def native_bytes(image_folder,manifest,expected):
  rootfs=Path(image_folder)/manifest['artifacts']['rootfs_squashfs']['file'];require(sha(rootfs)==manifest['artifacts']['rootfs_squashfs']['sha256'],'native_rootfs_binding')
  linux='/mnt/'+rootfs.drive[0].lower()+rootfs.as_posix()[2:]
  proc=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','unsquashfs','-cat',linux,native.lstrip('/')],capture_output=True,timeout=30)
  require(proc.returncode==0 and hashlib.sha256(proc.stdout).hexdigest()==expected,'native_helper_binding');return proc.stdout
 oldnative=native_bytes(prior['images']['f367']['directory'],oldmanifest,prior['runtime_bindings'][native]);newnative=native_bytes(folder,m,q['runtime_bindings'][native])
 require(newnative.replace(q['runtime_bindings'][qdrv].encode(),prior['runtime_bindings'][qdrv].encode())==oldnative,'native_shell_changed_beyond_qdrv_hash')
 old=prior['images']['f365'];require(all(q['recovery'][key]==old[key] for key in ('sha256','bytes','version','kernel_build')),'f365_fallback')
 store=Path(prior['store']['path']).read_bytes();require(hashlib.sha256(store).hexdigest()==prior['store']['sha256']==q['preserved_store']['sha256'],'store_hash')
 require(len(data)<worker.baseline.PREFIX,'slot_fit');prefix=data+b'\xff'*(worker.baseline.PREFIX-len(data));full=prefix+store
 require(image_to_dict(validate_bootbase_slot('f367r7',data,worker.baseline.SLOT))['accepted_by_contract'],'bootbase')
 require(worker.baseline.crc(full)==q['full_slot']['crc32'] and hashlib.sha256(full).hexdigest()==q['full_slot']['sha256'],'fullslot')
 known=folder/'known_hosts.f367';require(known.read_bytes()==Path(old['known_hosts_path']).read_bytes(),'ssh_identity')
 item=dict(directory=str(folder),base=image.name.removesuffix('.webformat.bin'),path=str(image),bytes=len(data),sha256=q['artifact']['sha256'],manifest_sha256=q['manifest_sha256'],version=q['product_version'],known_hosts='known_hosts.f367',known_hosts_path=str(known),kernel_build=old['kernel_build'],marker=old['marker'],crc32=worker.baseline.crc(data),prefix_crc32=worker.baseline.crc(prefix),full_slot_crc32=worker.baseline.crc(full),full_slot_sha256=hashlib.sha256(full).hexdigest(),preserved_store_sha256=prior['store']['sha256'],full_slot_scope='firmware prefix plus exact seq2 store')
 return q,item,m,refs,read(campaign['static_profile_qualification']['path'])

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--previous-plan',type=Path,required=True);p.add_argument('--completed-run',type=Path,required=True);p.add_argument('--candidate-result',type=Path,required=True);p.add_argument('--output-dir',type=Path);a=p.parse_args()
 prior=worker.previous.load_plan(a.previous_plan,sha(a.previous_plan));closed=read(a.completed_run)
 require(closed['status']=='FAIL_F367_WITH_F365_RETURN' and closed['error']=='control_failed_enter-dfs','previous_policy_clock_rejection')
 require(closed['writer']['image']==prior['images']['f367']['sha256'] and closed['writer']['byte_compare'] is True,'previous_image_binding')
 require(closed['baseline_returned'] is True and closed['returned_identity']['boot_id']=='bdaa516c-f61f-4f0a-bd94-c243f8c4ecdb','current_f365_boot')
 require(closed['restore_writer']['image']==prior['images']['f365']['sha256'] and closed['restore_writer']['byte_compare'] is True and closed['restore_writer']['full_slot_crc32']=='118901d4','current_f365_readback')
 require(closed['returned_store']['sha256']==prior['store']['sha256'] and closed['returned_configuration']['sequence']==2 and closed['returned_configuration']['active_sha256']==prior['boot_acceptance']['payload_sha256'],'current_store_config')
 require(closed['containment_confirmed'] is True and closed['retain_lease_required'] is False and closed['flash_command_in_flight'] is False and closed['watchdog_may_remain_armed'] is False,'previous_session_closed')
 require(closed['uart']['semantic_capture']['complete'] is True and closed['uart']['semantic_capture']['dropped_bytes']==0,'physical_capture_qualified')
 platform=Path(closed['return_platform']['result']);require(sha(platform)==closed['return_platform']['sha256'],'platform_hash');status=read(platform)
 require(status['status']=='PASS' and len(status['checks'])==27 and all(v is True for v in status['checks'].values()),'return_platform')
 q,image,manifest,refs,static=bind_image(a.candidate_result,prior)
 pins=dict(prior['sources']);files=[Path(__file__).resolve(),a.previous_plan.resolve(),a.completed_run.resolve(),a.candidate_result.resolve(),platform,Path(image['path']),Path(q['manifest']),Path(image['known_hosts_path']),Path(static['artifact']['path']),ROOT/'tools/f367r7_campaign_worker.py',ROOT/'tools/run_f367r7_campaign.py',ROOT/'tools/run_f367r7_campaign.ps1',*(Path(ref['path']) for ref in refs)]
 for source,digest in manifest['source']['inputs'].items():require(sha(source)==digest,'candidate_input_drift');files.append(Path(source).resolve())
 for source,digest in static['source_pins'].items():require(sha(source)==digest,'static_input_drift');files.append(Path(source).resolve())
 for ref in refs:
  for source,digest in read(ref['path'])['source_pins'].items():require(sha(source)==digest,'clock_capture_input_drift');files.append(Path(source))
 files.extend([ROOT/'tools/f367r7_clock_capture.py',ROOT/'tools/test_f367r7_clock_capture.py'])
 for file in files:pins[str(file.resolve())]=sha(file)
 require(worker.Host.__bases__==(worker.previous.Host,),'r7_host_not_narrow_subclass')
 require(all(sha(path)==digest for path,digest in pins.items()),'source_drift')
 out=(a.output_dir or ROOT/'outputs/preflight'/('f367r7-campaign-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve();require(not out.exists(),'immutable_output');out.mkdir(parents=True,exist_ok=False)
 plan=copy.deepcopy(prior);plan.update(runtime_revision='F367r7',repeat_scope='one-f367r7-clock-observation-trial',clock_observation_revision=7,
  images={'f367':image,'f365':prior['images']['f365']},runtime_bindings=q['runtime_bindings'],sources=pins,
  candidate_qualification=dict(path=str(a.candidate_result.resolve()),sha256=sha(a.candidate_result)),
  current_f365_return=dict(path=str(a.completed_run.resolve()),sha256=sha(a.completed_run),boot_id=closed['returned_identity']['boot_id']),
  clock_observation_test=refs[0],clock_json_test=refs[1],host_clock_capture_test=refs[2],clock_capture_fields=list(worker.clock_capture.FIELDS),
  host_delta=dict(host_reused_from='F367r6',host_clock_capture_tests=2,previous_tests_rerun=False,qualified_banks_rerun=False,new_hardware_actions=False),
  changed_scope='Only conservative clock publication/guard observations and host numeric capture; admission and deadline producers unchanged, R6 static helper, shell, V3 observer, phase2 gate, UART2 and dispatcher reused')
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=sha(path);worker.load_plan(path,digest)
 report=dict(status='PASS_OFFLINE_F367R7_CAMPAIGN_PLAN',plan=str(path),plan_sha256=digest,source_pins=len(pins),candidate_sha256=image['sha256'],full_slot_crc32=image['full_slot_crc32'],fallback_sha256=prior['images']['f365']['sha256'],hardware_actions=False,banks_rerun=False,host_capture_tests=2)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='ascii');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
