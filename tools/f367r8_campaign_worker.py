"""R8 setter-mode binding; all R5/V3 transport, phase and return behavior is reused."""
from pathlib import Path
import argparse,json,os
import f367r7_campaign_worker as previous
import f367r7_clock_capture as clock_capture
Host=previous.Host
core=previous.core
capture=previous.capture
baseline=previous.baseline
require=previous.require
claim_once=previous.claim_once
SCHEMA='openmitrastar.f367r8-mode-contract-image/v1'
STATUS='PASS_OFFLINE_F367R8_MODE_CONTRACT_IMAGE'

def load_plan(path,digest):
    plan=core.load_plan(path,digest)
    require(plan.get('clock_observation_revision')==7,'r7_clock_capture_revision')
    require(plan.get('runtime_revision')=='F367r8' and plan.get('activate_timeout_seconds')==240 and plan.get('uart_semantic_capture_revision')==2,'r7_host_scope')
    require(plan.get('host_phase_gate_revision')==2 and plan.get('readonly_guard_revision')==3 and plan.get('readonly_guard_retries')==1 and plan.get('readonly_retry_roles')==['snapshot','owner'],'r7_reused_host_contract')
    require(plan.get('repeat_scope')=='one-f367r8-mode-contract-trial' and plan.get('max_completed_executions')==1 and plan.get('initial_target52_readback_required') is True,'r7_single_operation')
    ref=plan['candidate_qualification'];require(baseline.sha(ref['path'])==ref['sha256'],'r7_qualification_hash')
    q=json.loads(Path(ref['path']).read_text(encoding='utf-8'));image=plan['images']['f367']
    require(q['schema']==SCHEMA and q['status']==STATUS and q['campaign']['runtime_revision']=='F367r8','r7_qualification_scope')
    require(q['artifact']['sha256']==image['sha256'] and q['artifact']['bytes']==image['bytes'] and q['manifest_sha256']==image['manifest_sha256'] and q['full_slot']['crc32']==image['full_slot_crc32'],'r7_exact_image')
    require(q['runtime_bindings']==plan['runtime_bindings'],'r7_runtime_binding')
    require(q['campaign']['regulatory_publication']=='OEM_SUBIO14_SINGLE_CHANNEL52_BEFORE_NATIVE_START' and q['campaign']['target52_readback_before_prepare'] is True,'r7_regulatory_contract')
    for field in ('static_profile_qualification','static_profile_target_probe','clock_observation_test','clock_json_test','mode_contract_test'):
        ref=q['campaign'][field];require(baseline.sha(ref['path'])==ref['sha256'],'r7_static_evidence_hash')
    for module in (core,capture,previous,clock_capture,previous.previous.previous.observation,previous.previous.previous.observation.phases):
        file=str(Path(module.__file__).resolve());require(plan['sources'].get(file)==baseline.sha(file),'r7_reused_source')
    require(plan['sources'].get(str(Path(__file__).resolve()))==baseline.sha(__file__),'r7_worker_binding')
    return plan

def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--output-dir',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
    plan=load_plan(a.plan,a.plan_sha256)
    if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID_F367R8_MODE_CONTRACT',hardware_actions=False)));return 0
    require(os.environ.get('OM_F367_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==core.EVIDENCE_ROOT.resolve(),'owning_launcher_required')
    claim_once(plan,a.plan_sha256)
    return core.run(plan,a.output_dir,host_factory=Host,uart_factory=capture.Uart)
if __name__=='__main__':raise SystemExit(main())
