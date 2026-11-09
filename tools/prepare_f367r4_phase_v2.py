"""Same sealed R4 firmware; bind only the phase-scoped host-gate correction."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,subprocess,sys
import f367r4_phase_worker_v2 as worker

ROOT=worker.core.ROOT
def sha(path):return worker.baseline.sha(path)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def require(value,reason):worker.require(value,reason)

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--previous-plan',type=Path,required=True);p.add_argument('--completed-run',type=Path,required=True);p.add_argument('--output-dir',type=Path);a=p.parse_args()
 prior=worker.previous.load_plan(a.previous_plan,sha(a.previous_plan));closed=read(a.completed_run)
 require(closed['status']=='FAIL_F367_WITH_F365_RETURN' and closed['error']=='regulatory_context_changed','previous_host_gate_failure')
 require(closed['writer']['image']==prior['images']['f367']['sha256'] and closed['writer']['byte_compare'] is True,'same_r4_image')
 require(closed['baseline_returned'] is True and closed['returned_identity']['boot_id']=='cc25fdd6-25da-45f9-bf1f-5ddd61920475','current_f365_return')
 require(closed['restore_writer']['image']==prior['images']['f365']['sha256'] and closed['restore_writer']['byte_compare'] is True and closed['restore_writer']['full_slot_crc32']=='118901d4','f365_readback')
 require(closed['returned_store']['sha256']==prior['store']['sha256'] and closed['returned_configuration']['sequence']==2 and closed['returned_configuration']['active_sha256']==prior['boot_acceptance']['payload_sha256'],'f365_store_config')
 require(closed['containment_confirmed'] is True and closed['retain_lease_required'] is False and closed['flash_command_in_flight'] is False and closed['watchdog_may_remain_armed'] is False,'closed_hardware_session')
 platform=Path(closed['return_platform']['result']);require(sha(platform)==closed['return_platform']['sha256'],'platform_hash')
 result=read(platform);require(result['status']=='PASS' and len(result['checks'])==27 and all(v is True for v in result['checks'].values()),'f365_platform')
 snapshot_path=a.completed_run.parent/'campaign-progress.json';snapshot=read(snapshot_path)['snapshot']
 require(snapshot['channel']==36 and snapshot['filter_bw']==80 and snapshot['configured']==snapshot['region_eu']==snapshot['region_es']==1 and snapshot['doth']==snapshot['tpc']==snapshot['ready']==snapshot['generation']==0,'observed_initial_phase')
 require(snapshot['provider_started']==snapshot['provider_hardware_ready']==1 and snapshot['jobs_completed']==289 and snapshot['errors']==snapshot['control_fault']==snapshot['tx_fault_latched']==0,'observed_native_success')
 pins=dict(prior['sources'])
 files=[Path(__file__).resolve(),a.previous_plan.resolve(),a.completed_run.resolve(),platform,snapshot_path,ROOT/'tools/f367_phase_gate_v2.py',ROOT/'tools/f367r4_phase_worker_v2.py',ROOT/'tools/run_f367r4_phase_v2.py',ROOT/'tools/run_f367r4_phase_v2.ps1',ROOT/'tools/test_f367_phase_gate_v2.py']
 for file in files:pins[str(file.resolve())]=sha(file)
 out=(a.output_dir or ROOT/'outputs/preflight'/('f367r4-phase-v2-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve();require(not out.exists(),'immutable_output');out.mkdir(parents=True,exist_ok=False)
 run=subprocess.run([sys.executable,'-m','unittest','discover','-s','tools','-p','test_f367_phase_gate_v2.py','-v'],cwd=ROOT,capture_output=True,timeout=30)
 (out/'tests.stdout').write_bytes(run.stdout);(out/'tests.stderr').write_bytes(run.stderr);require(run.returncode==0,'phase_delta_tests')
 require(all(sha(path)==digest for path,digest in pins.items()),'source_drift')
 plan=copy.deepcopy(prior);plan.update(host_phase_gate_revision=2,sources=pins,
  current_f365_return=dict(path=str(a.completed_run.resolve()),sha256=sha(a.completed_run),boot_id=closed['returned_identity']['boot_id']),
  phase_gate_contract=dict(
   always_required=['configured=1','region_eu=1','region_es=1','provider_started=1','provider_hardware_ready=1','live advancing acquisition','no hardware/engine/control/TX faults'],
   initial_exception='Only before a confirmed enter-dfs, channel36/BW80, no CAC/NOP/software injection: DOTH/TPC0 and READY/generation0 are permitted without altering evidence.',
   entry_confirmation='Track only successful enter-dfs helper return; the pinned helper executes PREPARE52/TX-off, enables DOTH/TPC, sets mode/filter/channel52 and verifies readback.',
   after_entry='DOTH/TPC must stay1, including fallback36/NOP; valid CAC and DFS transmission require READY and a positive generation. Non-DFS fallback may have READY/generation0.',
   timer_and_rejection_logic='Original Campaign.run/wait/cac/rejection/timer methods reused unchanged; rejected NOP reentry never changes phase history.'),
  host_only_delta=dict(image_changed=False,firmware_rebuilt=False,banks_rerun=False,phase_delta_tests=6,original_failure_preserved=True))
 require(plan['images']==prior['images'] and plan['runtime_bindings']==prior['runtime_bindings'] and plan['supervisor']==prior['supervisor'],'firmware_or_deadline_changed')
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=sha(path);worker.load_plan(path,digest)
 report=dict(status='PASS_OFFLINE_F367R4_PHASE_GATE_V2',plan=str(path),plan_sha256=digest,source_pins=len(pins),image_sha256=plan['images']['f367']['sha256'],image_changed=False,hardware_actions=False,phase_delta_tests=6,banks_rerun=False)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='ascii');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
