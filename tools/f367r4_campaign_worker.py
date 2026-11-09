"""F367r4 binding; reuse the qualified R3 host, UART2 and all return gates."""
from pathlib import Path
import argparse,json,os
from f367r3_campaign_worker import Host,core,capture,claim_once,require,baseline

SCHEMA='openmitrastar.f367r4-hostlink-ack-image/v1'
STATUS='PASS_OFFLINE_F367R4_HOSTLINK_ACK_IMAGE'

def load_plan(path,digest):
 plan=core.load_plan(path,digest)
 require(plan.get('runtime_revision')=='F367r4' and plan.get('activate_timeout_seconds')==240 and plan.get('uart_semantic_capture_revision')==2,'r4_host_scope')
 require(plan.get('repeat_scope')=='one-f367r4-hostlink-ack-trial' and plan.get('max_completed_executions')==1,'r4_single_operation')
 ref=plan['candidate_qualification'];require(baseline.sha(ref['path'])==ref['sha256'],'r4_qualification_hash')
 q=json.loads(Path(ref['path']).read_text(encoding='utf-8'))
 require(q['schema']==SCHEMA and q['status']==STATUS and q['campaign']['runtime_revision']=='F367r4','r4_qualification_scope')
 image=plan['images']['f367']
 require(q['artifact']['sha256']==image['sha256'] and q['artifact']['bytes']==image['bytes'] and q['manifest_sha256']==image['manifest_sha256'] and q['full_slot']['crc32']==image['full_slot_crc32'],'r4_exact_image')
 for module in (core,capture):
  file=str(Path(module.__file__).resolve());require(plan['sources'].get(file)==baseline.sha(file),'r4_reused_source')
 require(plan['sources'].get(str(Path(__file__).resolve()))==baseline.sha(__file__),'r4_worker_binding')
 return plan

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--output-dir',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
 plan=load_plan(a.plan,a.plan_sha256)
 if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID_F367R4',hardware_actions=False)));return 0
 require(os.environ.get('OM_F367_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==core.EVIDENCE_ROOT.resolve(),'owning_launcher_required')
 claim_once(plan,a.plan_sha256)
 return core.run(plan,a.output_dir,host_factory=Host,uart_factory=capture.Uart)
if __name__=='__main__':raise SystemExit(main())
