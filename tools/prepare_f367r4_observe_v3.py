"""Bind the new host observer only; sealed R4 firmware and deadlines are reused."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json,subprocess,sys
import f367r4_observer_worker_v3 as worker

ROOT=worker.core.ROOT
def sha(path):return worker.baseline.sha(path)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def require(value,reason):worker.require(value,reason)

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--previous-plan',type=Path,required=True);p.add_argument('--completed-run',type=Path,required=True);p.add_argument('--output-dir',type=Path);a=p.parse_args()
 prior=worker.previous.load_plan(a.previous_plan,sha(a.previous_plan));closed=read(a.completed_run)
 require(closed['status']=='FAIL_F367_WITH_F365_RETURN' and closed['error']=='TimeoutExpired','previous_observer_failure')
 require(closed['writer']['image']==prior['images']['f367']['sha256'] and closed['writer']['byte_compare'] is True,'same_r4_image')
 require(closed['baseline_returned'] is True and closed['returned_identity']['boot_id']=='66b4b270-7e58-467a-8e51-7b002970e2c3','current_f365_return')
 require(closed['restore_writer']['image']==prior['images']['f365']['sha256'] and closed['restore_writer']['byte_compare'] is True and closed['restore_writer']['full_slot_crc32']=='118901d4','f365_readback')
 require(closed['returned_store']['sha256']==prior['store']['sha256'] and closed['returned_configuration']['sequence']==2 and closed['returned_configuration']['active_sha256']==prior['boot_acceptance']['payload_sha256'],'f365_store_config')
 require(closed['containment_confirmed'] is True and closed['retain_lease_required'] is False and closed['flash_command_in_flight'] is False and closed['watchdog_may_remain_armed'] is False,'closed_hardware_session')
 platform=Path(closed['return_platform']['result']);require(sha(platform)==closed['return_platform']['sha256'],'platform_hash')
 status=read(platform);require(status['status']=='PASS' and len(status['checks'])==27 and all(v is True for v in status['checks'].values()),'f365_platform')
 last_snapshot=a.completed_run.parent/'campaign-progress.json';snap=read(last_snapshot)['snapshot']
 require(snap['jobs_completed']==14334 and snap['errors']==snap['control_fault']==snap['tx_fault_latched']==0 and snap['channel']==36,'last_healthy_snapshot')
 pins=dict(prior['sources'])
 files=[Path(__file__).resolve(),a.previous_plan.resolve(),a.completed_run.resolve(),platform,last_snapshot,ROOT/'tools/f367_readonly_guard_v3.py',ROOT/'tools/f367r4_observer_worker_v3.py',ROOT/'tools/run_f367r4_observe_v3.py',ROOT/'tools/run_f367r4_observe_v3.ps1',ROOT/'tools/test_f367_readonly_guard_v3.py']
 for file in files:pins[str(file.resolve())]=sha(file)
 out=(a.output_dir or ROOT/'outputs/preflight'/('f367r4-observe-v3-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve();require(not out.exists(),'immutable_output');out.mkdir(parents=True,exist_ok=False)
 run=subprocess.run([sys.executable,'-m','unittest','discover','-s','tools','-p','test_f367_readonly_guard_v3.py','-v'],cwd=ROOT,capture_output=True,timeout=30)
 (out/'tests.stdout').write_bytes(run.stdout);(out/'tests.stderr').write_bytes(run.stderr);require(run.returncode==0,'readonly_guard_delta_tests')
 require(all(sha(path)==digest for path,digest in pins.items()),'source_drift')
 plan=copy.deepcopy(prior);plan.update(readonly_guard_revision=3,readonly_guard_retries=1,readonly_retry_roles=['snapshot','owner'],sources=pins,
  current_f365_return=dict(path=str(a.completed_run.resolve()),sha256=sha(a.completed_run),boot_id=closed['returned_identity']['boot_id']),
  readonly_resilience=dict(
   trigger='Only a timed-out local PowerShell guard whose child has been killed/reaped and confirmed contained.',
   retry='At most one complete readonly state+owner resample; discard partial state and rerun every original guard/hash/identity check.',
   abort=['second timeout','uncontained child','guard rc failure','invalid guard output','source/lease/identity failure','existing phase/session deadline expired'],
   mutations='No retries for activate, enter-dfs, software-radar, STOP, firmware writes, or any other control/SSH operation.',
   deadlines='Kernel/CAC/NOP and supervisor horizons are unchanged; readonly transport budgets are bounded by the original host phase/session deadlines.',
   evidence='Safe executable/operation role, duration, timeout, rc, child containment and redacted output; never full argv or nonce.'),
  host_observation_delta=dict(image_changed=False,firmware_rebuilt=False,banks_rerun=False,tests=6,original_failure_preserved=True))
 require(plan['images']==prior['images'] and plan['runtime_bindings']==prior['runtime_bindings'] and plan['supervisor']==prior['supervisor'],'firmware_changed')
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=sha(path);worker.load_plan(path,digest)
 report=dict(status='PASS_OFFLINE_F367R4_READONLY_GUARD_V3',plan=str(path),plan_sha256=digest,source_pins=len(pins),image_sha256=plan['images']['f367']['sha256'],hardware_actions=False,image_changed=False,delta_tests=6,banks_rerun=False)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='ascii');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
