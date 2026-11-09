"""Bind the real F367 image, native-acquisition acceptance and long campaign.

Local qualification only. No hardware execution option or guessed image hash.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil,subprocess,sys
import f365_install_contract as base
import f365_install_executor as previous
import f367_campaign_executor as executor
import f367_aelita_harness as aelita
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict

ROOT=base.ROOT
SUPERVISOR_PROOF=ROOT/'outputs/kernel-port/f367-supervisor-20260922T115143Z/result.json'
ACCEPTANCE_SHA='9201514a074decb9987cdaa174f25c19739ddc083e9a842179fec77cc633fb87'
CLIENT_CLEANUP_PROOF=ROOT/'outputs/preflight/f367-aelita-dispatch-review-20260922T122958Z/result.json'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def image_binding(path,prior):
 q=read(path);campaign=q['campaign']
 require=base.require
 require(q['status'].startswith('PASS_OFFLINE_F367') and q['reproducible'] is True and q['bootbase']=='PASS' and q['slot_fit'] is True,'f367_image_qualification')
 expected=dict(callback_authority=1,bootstrap_channel=36,bootstrap_bandwidth=80,dfs_channel=52,dfs_bandwidth=20,escape_channel=36,quarantine_ms=1800000,cac_ms=70000,nop_ms=1800000,supervisor_total_ms=5400000)
 require(all(campaign.get(key)==value for key,value in expected.items()),'f367_campaign_scope')
 require(campaign['supervisor']['path']=='/usr/sbin/om-watchdog-supervisor-f367' and campaign['supervisor']['sha256']=='ecd861a42812a8516f81e38fdad081089639f77a61c56335bf6c1110a926a477','f367_supervisor')
 accept=campaign['acquisition_acceptance'];require(accept['sha256']==ACCEPTANCE_SHA==base.sha(accept['path']),'accepted_r3_acquisition')
 accepted=read(accept['path']);require(accepted['status']=='PASS_F366R3_NATIVE_ACQUISITION_WITH_F365_RETURN_ADDENDUM' and accepted['all_other_gates_unchanged'] is True,'accepted_r3_scope')
 artifact=q['artifact'];image=Path(artifact['path']).resolve(strict=True);data=image.read_bytes();manifest=image.parent/'manifest.json'
 require(len(data)==artifact['bytes'] and base.sha(image)==artifact['sha256'] and base.sha(manifest)==q['manifest_sha256'],'f367_immutable_image')
 require(re.fullmatch('[A-Za-z0-9._-]+',q['product_version']) and '-f367-' in q['product_version'],'f367_version')
 old=prior['images']['f365'];recovery=q['recovery'];require(recovery['sha256']==old['sha256'] and recovery['bytes']==old['bytes'] and recovery['version']==old['version'] and recovery['kernel_build']==old['kernel_build'],'f365_fallback_scope')
 require(0<len(data)<base.PREFIX,'f367_slot_fit');contract=image_to_dict(validate_bootbase_slot('f367',data,base.SLOT))
 require(contract['accepted_by_contract'] and contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000','f367_bootbase')
 store=Path(prior['store']['path']).read_bytes();prefix=data+b'\xff'*(base.PREFIX-len(data));full=prefix+store
 require(base.crc(full)==q['full_slot']['crc32'] and hashlib.sha256(full).hexdigest()==q['full_slot']['sha256'],'preserved_store_fullslot')
 known=image.parent/'known_hosts.f367';require(known.is_file() and known.read_bytes()==Path(old['known_hosts_path']).read_bytes(),'f367_ssh_key')
 bindings=dict(q['runtime_bindings']);require(bindings.get('/usr/sbin/om-watchdog-supervisor-f367')==campaign['supervisor']['sha256'],'runtime_supervisor_binding')
 for helper in ('om-f367-control','om-f367-status'):
  require('/usr/sbin/'+helper in bindings,'f367_helper_binding')
 item=dict(directory=str(image.parent),base=image.name.removesuffix('.webformat.bin'),path=str(image),bytes=len(data),sha256=artifact['sha256'],manifest_sha256=q['manifest_sha256'],version=q['product_version'],known_hosts='known_hosts.f367',known_hosts_path=str(known),kernel_build=old['kernel_build'],marker=old['marker'],crc32=base.crc(data),prefix_crc32=base.crc(prefix),full_slot_crc32=base.crc(full),full_slot_sha256=hashlib.sha256(full).hexdigest(),preserved_store_sha256=prior['store']['sha256'],full_slot_scope='firmware prefix plus exact seq2 store')
 return item,bindings,q,accepted

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--candidate-result',type=Path,required=True);p.add_argument('--previous-campaign',type=Path,required=True);p.add_argument('--baseline-plan',type=Path,required=True);p.add_argument('--output-dir',type=Path);args=p.parse_args()
 base.require(shutil.disk_usage('C:/').free>500*1024*1024 and shutil.disk_usage('D:/').free>500*1024*1024,'disk_floor')
 prior=previous.load_plan(args.baseline_plan,base.sha(args.baseline_plan));candidate,bindings,qualified,accepted=image_binding(args.candidate_result,prior)
 before=read(args.previous_campaign);base.require(str(args.previous_campaign.resolve()) in accepted['evidence'] and accepted['evidence'][str(args.previous_campaign.resolve())]==base.sha(args.previous_campaign),'return_evidence_binding')
 base.require(before['baseline_returned'] is True and before['restore_writer']['image']==prior['images']['f365']['sha256'] and before['containment_confirmed'] is True and before['retain_lease_required'] is False and before['flash_command_in_flight'] is False,'previous_hardware_session_closed')
 sup=read(SUPERVISOR_PROOF);base.require(sup['status']=='PASS_OFFLINE_F367_SUPERVISOR' and sup['reproducible'] is True and base.sha(sup['artifact']['path'])==sup['artifact']['sha256'],'supervisor_qualification')
 cleanup=read(CLIENT_CLEANUP_PROOF);base.require(base.sha(CLIENT_CLEANUP_PROOF)=='064f4fb9be0499442ba64e8a3c6a429869947ed67c8c285f13e6785e3e525625' and cleanup['status']=='PASS_OFFLINE_F367_AELITA_DISPATCH_CLEANUP_DELTA' and cleanup['tests']['count']==2,'client_cleanup_delta')
 for source,digest in cleanup['sources'].items():base.require(base.sha(source)==digest,'client_cleanup_source_drift')
 base.require(base.sha(cleanup['tests']['path'])==cleanup['tests']['sha256'],'client_cleanup_test_hash')
 config=read(ROOT/'configs/f367_aelita_client.json');aelita.validate_config(config)
 out=(args.output_dir or ROOT/'outputs/preflight'/('f367-campaign-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve();base.require(not out.exists(),'immutable_output');out.mkdir(parents=True,exist_ok=False)
 executor.EVIDENCE_ROOT.mkdir(parents=True,exist_ok=True)
 for entry in (executor.EVIDENCE_ROOT,*executor.EVIDENCE_ROOT.parents):base.require(not entry.is_symlink() and not getattr(entry,'is_junction',lambda:False)(),'evidence_reparse')
 files={Path(path).resolve() for path in prior['sources']}
 files.update(Path(module.__file__).resolve() for module in sys.modules.values() if getattr(module,'__file__',None) and Path(module.__file__).resolve().is_relative_to(ROOT/'tools'))
 names=('prepare_f367_campaign.py','f367_campaign_executor.py','f367_campaign.py','f367_aelita_dispatcher.py','f367_aelita_client_r2.ps1','f367_aelita_router_snapshot.sh','f367_aelita_harness.py','run_aelita_2g_wpa2_runtime_psk_once.py','aelita_ssh_policy.py','openmitrastar_l2_speed_server.py','f366r3_reset_observation.py','f366r3_source_freeze.ps1','f367_hardware_context.ps1','assert_f367_context.ps1','run_f367_campaign.py','run_f367_campaign.ps1','test_f367_campaign_logic.py','test_f367_aelita_dispatcher.py','test_f367_aelita_r2.ps1','test_f367_context.ps1','test_f367_control_receipt.py')
 files.update(ROOT/'tools'/name for name in names)
 files.update([args.candidate_result.resolve(),args.previous_campaign.resolve(),args.baseline_plan.resolve(),Path(candidate['path']),Path(candidate['directory'])/'manifest.json',Path(candidate['known_hosts_path']),SUPERVISOR_PROOF,Path(sup['artifact']['path']),ROOT/'configs/f367_aelita_client.json',ROOT/config['client']['known_hosts'],ROOT/config['client']['key'],Path(qualified['campaign']['acquisition_acceptance']['path'])])
 files.update([CLIENT_CLEANUP_PROOF,Path(cleanup['tests']['path']),*(Path(source) for source in cleanup['sources'])])
 for path,digest in sup['sources'].items():base.require(base.sha(path)==digest,'supervisor_source_drift');files.add(Path(path).resolve())
 manifest=read(Path(candidate['directory'])/'manifest.json')
 for path,digest in manifest['source']['inputs'].items():base.require(base.sha(path)==digest,'image_input_drift');files.add(Path(path).resolve())
 pins={str(path):base.sha(path) for path in sorted(files)};tests={}
 for filename in ('test_f367_campaign_logic.py','test_f367_aelita_dispatcher.py','test_f367_control_receipt.py'):
  run=subprocess.run([sys.executable,'-m','unittest','discover','-s','tools','-p',filename,'-v'],cwd=ROOT,capture_output=True,timeout=60)
  (out/(filename+'.stdout')).write_bytes(run.stdout);(out/(filename+'.stderr')).write_bytes(run.stderr);base.require(run.returncode==0,'delta_test_'+filename);tests[filename]=dict(passed=True,log=str(out/(filename+'.stderr')))
 for filename in ('test_f367_aelita_r2.ps1','test_f367_context.ps1'):
  result=out/(filename+'.json');run=subprocess.run([executor.desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools'/filename),'-ResultPath',str(result)],env=executor.desktop_ps.environment(),capture_output=True,timeout=60)
  (out/(filename+'.stdout')).write_bytes(run.stdout);(out/(filename+'.stderr')).write_bytes(run.stderr);base.require(run.returncode==0 and read(result)['passed'],'delta_test_'+filename);tests[filename]=dict(path=str(result),sha256=base.sha(result),passed=True)
 base.require(all(base.sha(path)==digest for path,digest in pins.items()),'source_drift_during_delta')
 plan={key:value for key,value in prior.items() if key not in ('images','sources','tests','success_policy','failure_policy','limits','baseline_proofs')}
 plan.update(schema='openmitrastar.f367-campaign-plan/v1',status='PASS_OFFLINE_REVIEWED_EXECUTOR',images={'f367':candidate,'f365':prior['images']['f365']},runtime_bindings=bindings,sources=pins,tests=tests,
  candidate_qualification=dict(path=str(args.candidate_result.resolve()),sha256=base.sha(args.candidate_result)),acquisition_acceptance=qualified['campaign']['acquisition_acceptance'],
  previous_campaign=dict(path=str(args.previous_campaign.resolve()),sha256=base.sha(args.previous_campaign),failed_marker_result_preserved=True,returned_boot_id=before['returned_identity']['boot_id']),
  aelita_config=config,client_cleanup_qualification=dict(path=str(CLIENT_CLEANUP_PROOF),sha256=base.sha(CLIENT_CLEANUP_PROOF),tests=2,reused_without_rerun=True),active_client_receipt='Same-owner live installation/boot/CAC receipt; no fabricated completed installation result',
  client_http_firewall_scope=dict(protocol='TCP',local_ipv4='192.168.1.49',local_port=8081,remote='observed Wi-Fi17 IPv4 only',lifetime='one client gate; exact run-name/group cleanup',principal_router_changes=False),
  supervisor=sup['artifact'],supervisor_qualification=dict(path=str(SUPERVISOR_PROOF),sha256=base.sha(SUPERVISOR_PROOF)),callback_authority=1,dfs_primary=52,dfs_bandwidth=20,watchdog_session_ms=5400000,
  outer_timeout_seconds=7500,context_ttl_seconds=7800,installation_reserve_seconds=900,return_reserve_seconds=900,host_stop_reset_margin_seconds=120,watchdog_arm_allowed=True,radio_tests_allowed=True,always_restore_f365=True,
  evidence_root=str(executor.EVIDENCE_ROOT.resolve()),known_hosts=prior['images']['f365']['known_hosts_path'],source_freeze='Read-only handles held across entire PS5 execution',host_keep_awake='Scoped SetThreadExecutionState restored on exit',
  success_policy='One long-owner run: quarantine1800, real CAC70 with continuous generation, two source-bound AELITA client gates around SOFTWARE_INJECTION/NOP1800/newCAC70; STOP/CEASE and exact F365 return. No RF-silence or calibrated-radar claim.',
  failure_policy='Preserve failing snapshots. Always attempt client restore and scoped HTTP cleanup. ABORT/CEASE without rmmod; observe reset, one serial recovery only if needed, exact F365 prefix return. Ambiguous flash completion blocks any new write.',
  limits=['Software injection is not calibrated RF radar detection','Quarantine1800 is this candidate recovery policy, not an asserted regulation','One owner, HEALTH lease5s, phases<=60s and absolute90min never renewed','No CPU-stop test and no principal-router configuration'])
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=base.sha(path);executor.load_plan(path,digest)
 result=dict(status='PASS_OFFLINE_F367_CAMPAIGN_EXECUTOR',plan=str(path),plan_sha256=digest,source_pins=len(pins),candidate_sha256=candidate['sha256'],fallback_sha256=prior['images']['f365']['sha256'],hardware_actions=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
