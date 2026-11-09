"""Same R4 firmware and phase gate; typed guard receipts and readonly retry."""
from pathlib import Path
import argparse,json,os
import f367r4_phase_worker_v2 as previous
import f367_readonly_guard_v3 as observation
core=previous.core
capture=previous.capture
baseline=previous.baseline
require=previous.require

def load_plan(path,digest):
 plan=previous.load_plan(path,digest)
 require(plan.get('readonly_guard_revision')==3 and plan.get('readonly_guard_retries')==1 and plan.get('readonly_retry_roles')==['snapshot','owner'],'observation_revision')
 source=str(Path(observation.__file__).resolve())
 require(plan['sources'].get(source)==baseline.sha(source),'observation_source')
 require(plan['sources'].get(str(Path(__file__).resolve()))==baseline.sha(__file__),'observation_worker_source')
 return plan

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--output-dir',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
 plan=load_plan(a.plan,a.plan_sha256)
 if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID_F367R4_READONLY_GUARD_V3',hardware_actions=False)));return 0
 require(os.environ.get('OM_F367_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==core.EVIDENCE_ROOT.resolve(),'owning_launcher_required')
 previous.claim_once(plan,a.plan_sha256)
 return core.run(plan,a.output_dir,host_factory=observation.Host,uart_factory=capture.Uart)
if __name__=='__main__':raise SystemExit(main())
