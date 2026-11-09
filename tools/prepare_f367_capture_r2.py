"""Seal one same-image repeat; reuse every previous PASS by hash, no test rerun."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,json
import f367_capture_r2_worker as worker

ROOT=worker.core.ROOT
CAPTURE_PROOF=ROOT/'outputs/preflight/f367-uart-capture-r2-20260922T130114Z/result.json'
CAPTURE_PROOF_SHA='14c5c390c4ab3c1bacbf3a934fb9072d6bce641fc4b9414b8837601c89dc464a'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def require(value,reason):worker.core.require(value,reason)
def sha(path):return worker.core.baseline.sha(path)

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--previous-plan',type=Path,required=True);p.add_argument('--completed-run',type=Path,required=True);p.add_argument('--output-dir',type=Path);args=p.parse_args()
 prior=worker.core.load_plan(args.previous_plan,sha(args.previous_plan))
 completed=read(args.completed_run)
 require(completed['schema']=='openmitrastar.f367-campaign-result/v1' and completed['status']=='FAIL_F367_WITH_F365_RETURN' and completed['error']=='control_timeout_activate','previous_attempt_scope')
 require(completed['writer']['image']==worker.IMAGE_SHA and completed['writer']['byte_compare'] is True and completed['writer']['full_slot_crc32']=='6f77010f','same_image_previous_attempt')
 require(completed['baseline_returned'] is True and completed['restore_writer']['image']==prior['images']['f365']['sha256'] and completed['restore_writer']['byte_compare'] is True and completed['restore_writer']['full_slot_crc32']=='118901d4','f365_return_required')
 require(completed['returned_identity']['boot_id']=='19f112a8-ae00-4c10-b6b2-21059aa35582','current_f365_return_boot')
 require(completed['containment_confirmed'] is True and completed['retain_lease_required'] is False and completed['flash_command_in_flight'] is False and completed['watchdog_may_remain_armed'] is False,'previous_session_not_closed')
 require(completed['returned_store']['sha256']==prior['store']['sha256'] and completed['returned_configuration']['sequence']==2 and completed['returned_configuration']['active_sha256']==prior['boot_acceptance']['payload_sha256'],'returned_config_store')
 platform=Path(completed['return_platform']['result']);require(sha(platform)==completed['return_platform']['sha256'],'return_platform_hash')
 status=read(platform);require(status['status']=='PASS' and len(status['checks'])==27 and all(v is True for v in status['checks'].values()),'return_platform_pass')
 require(sha(CAPTURE_PROOF)==CAPTURE_PROOF_SHA,'capture_qualification_hash')
 proof=read(CAPTURE_PROOF);require(proof['status']=='PASS_OFFLINE_F367_UART_CAPTURE_DELTA' and proof['tests']==4 and proof['extra_serial_reads']==proof['extra_serial_writes']==0 and proof['original_sources_unchanged'] is True,'capture_delta_qualification')
 for source,digest in proof['sources'].items():require(sha(source)==digest,'capture_delta_source_drift')
 # All 150 original bindings remain; append only new host wrapper/capture inputs.
 pins=dict(prior['sources'])
 files=[args.previous_plan.resolve(),args.completed_run.resolve(),platform,CAPTURE_PROOF,Path(__file__).resolve(),ROOT/'tools/f367_capture_r2_worker.py',ROOT/'tools/run_f367_capture_r2.py',ROOT/'tools/run_f367_capture_r2.ps1',*(Path(source) for source in proof['sources'])]
 for file in files:pins[str(file.resolve())]=sha(file)
 plan=copy.deepcopy(prior);plan.update(uart_semantic_capture_revision=2,repeat_scope='one-same-image-capture-only-repeat',max_completed_executions=1,sources=pins,
  capture_delta=dict(qualification=str(CAPTURE_PROOF),sha256=sha(CAPTURE_PROOF),tests_reused=4,new_tests_run=0,image_rebuilt=False,changed_execution_input='UART capture class only; existing campaign/writer/recovery unchanged'),
  repeat_baseline=dict(path=str(args.completed_run.resolve()),sha256=sha(args.completed_run),status=completed['status'],returned_boot_id=completed['returned_identity']['boot_id']),
  expected_semantic_log='uart-semantic-r2.jsonl',capture_incomplete_blocks_pass=True)
 require(plan['images']==prior['images'] and plan['runtime_bindings']==prior['runtime_bindings'] and plan['supervisor']==prior['supervisor'],'noncapture_input_changed')
 out=(args.output_dir or ROOT/'outputs/preflight'/('f367-capture-r2-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve();require(not out.exists(),'immutable_output');out.mkdir(parents=True,exist_ok=False)
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=sha(path);worker.load_plan(path,digest)
 result=dict(status='PASS_OFFLINE_F367_CAPTURE_ONLY_REPEAT',plan=str(path),plan_sha256=digest,source_pins=len(pins),original_source_pins=len(prior['sources']),image_sha256=worker.IMAGE_SHA,image_changed=False,tests_rerun=False,hardware_actions=False,max_completed_executions=1)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii');print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
