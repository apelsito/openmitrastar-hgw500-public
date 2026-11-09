"""R5 image binding and initial OEM profile evidence; reuse the V3 host."""
from pathlib import Path
import argparse,json,os,time
import f367r4_observer_worker_v3 as previous
import f367_readonly_guard_v3 as observation

core=previous.core
capture=previous.capture
baseline=previous.baseline
require=previous.require
claim_once=previous.previous.claim_once
SCHEMA='openmitrastar.f367r5-regulatory-profile-image/v1'
STATUS='PASS_OFFLINE_F367R5_REGULATORY_PROFILE_IMAGE'
PUBLICATION='OMF367_PROFILE_PUBLISHED producer=OEM_SUBIO14 channel=52 active=1 dfs=1 passive=1 active_mask_unchanged=1'
FILTER='OMF367_NATIVE_FILTER_CONFIG radar_bw=80 setter=ieee80211-param-235 authority=1'
STARTED='OMF367_NATIVE_STARTED started=1 hardware_dirty=1 hardware_ready=1 authority=1'
PROFILE_FIELDS=('target52_present','target52_active','target52_dfs','target52_radar','profile_publish_allowed')

def publication_receipt(receipt):
    require(receipt.get('action')=='activate' and receipt.get('exit_code')==0 and receipt.get('timed_out') is False,'r5_activation_not_confirmed')
    lines=[row.get('text','') for row in receipt['streams']['stdout']['lines']]
    require(sum(line.startswith('OMF367_PROFILE_PUBLISHED') for line in lines)==1 and PUBLICATION in lines,'r5_publication_missing_or_ambiguous')
    require(lines.count(FILTER)==lines.count(STARTED)==1,'r5_native_markers_missing_or_ambiguous')
    # START_ATTEMPT is intentionally not an API boundary. The pinned program
    # invokes publish after FILTER_CONFIG and before the native enable API.
    require(lines.index(FILTER)<lines.index(PUBLICATION)<lines.index(STARTED),'r5_publication_order')
    return dict(status='PASS_CAPTURED_OEM_PROFILE_PUBLICATION',channel=52,active=1,dfs=1,passive=1,active_mask_unchanged=True,publication_count=1,order_basis='single stdout stream plus pinned native program',rf_detection_proven=False)

def initial_readback(row):
    require(all(type(row.get(key)) is int and row[key] in (0,1) for key in PROFILE_FIELDS),'r5_target52_fields_missing')
    require(row['target52_present']==row['target52_active']==row['target52_dfs']==1 and row['target52_radar']==0,'r5_target52_initial_classification')
    require(row['channel']==36 and row['filter_bw']==80 and row['software_injections']==row['nop_active']==row['cac_active']==row['cac_done']==0,'r5_initial_profile_context')
    return dict(status='PASS_INITIAL_TARGET52_READBACK',**{key:row[key] for key in PROFILE_FIELDS})

class Host(observation.Host):
    def raw_control(self,action,token=None,expected_rejection=None):
        result=super().raw_control(action,token,expected_rejection)
        if action=='activate':
            path=Path(result['receipt_path']);require(baseline.sha(path)==result['receipt_sha256'],'r5_activation_receipt_hash')
            evidence=publication_receipt(json.loads(path.read_text(encoding='ascii')))
            evidence.update(receipt_path=str(path),receipt_sha256=result['receipt_sha256'])
            core.save(self.out/'regulatory-publication.json',evidence)
            self.r5_publication_confirmed=True
        return result
    def snapshot(self):
        row=super().snapshot()
        if not getattr(self,'r5_initial_readback_confirmed',False):
            safe={key:row.get(key) for key in PROFILE_FIELDS+('channel','filter_bw','monotonic_ms','software_injections','nop_active','cac_active','cac_done')}
            core.save(self.out/'regulatory-initial-readback.json',dict(status='CAPTURED_BEFORE_VALIDATION',snapshot=safe))
            require(getattr(self,'r5_publication_confirmed',False),'r5_publication_not_confirmed')
            evidence=initial_readback(row);evidence['snapshot']=safe
            core.save(self.out/'regulatory-initial-readback.json',evidence)
            self.r5_initial_readback_confirmed=True
        return row
    def record(self,label,row):
        super().record(label,row)
        if 'monotonic_ms' in row:
            safe={key:row[key] for key in PROFILE_FIELDS+('monotonic_ms','channel','filter_bw','nop_active') if type(row.get(key)) is int}
            with (self.out/'regulatory-snapshots.jsonl').open('a',encoding='ascii') as stream:
                stream.write(json.dumps(dict(stage=label,host_monotonic_ms=round(time.monotonic()*1000),snapshot=safe))+'\n');stream.flush();os.fsync(stream.fileno())

def load_plan(path,digest):
    plan=core.load_plan(path,digest)
    require(plan.get('runtime_revision')=='F367r5' and plan.get('activate_timeout_seconds')==240 and plan.get('uart_semantic_capture_revision')==2,'r5_host_scope')
    require(plan.get('host_phase_gate_revision')==2 and plan.get('readonly_guard_revision')==3 and plan.get('readonly_guard_retries')==1 and plan.get('readonly_retry_roles')==['snapshot','owner'],'r5_reused_host_contract')
    require(plan.get('repeat_scope')=='one-f367r5-regulatory-profile-trial' and plan.get('max_completed_executions')==1 and plan.get('initial_target52_readback_required') is True,'r5_single_operation')
    ref=plan['candidate_qualification'];require(baseline.sha(ref['path'])==ref['sha256'],'r5_qualification_hash')
    q=json.loads(Path(ref['path']).read_text(encoding='utf-8'));image=plan['images']['f367']
    require(q['schema']==SCHEMA and q['status']==STATUS and q['campaign']['runtime_revision']=='F367r5','r5_qualification_scope')
    require(q['artifact']['sha256']==image['sha256'] and q['artifact']['bytes']==image['bytes'] and q['manifest_sha256']==image['manifest_sha256'] and q['full_slot']['crc32']==image['full_slot_crc32'],'r5_exact_image')
    require(q['runtime_bindings']==plan['runtime_bindings'],'r5_runtime_binding')
    require(q['campaign']['regulatory_publication']=='OEM_SUBIO14_SINGLE_CHANNEL52_BEFORE_NATIVE_START' and q['campaign']['target52_readback_before_prepare'] is True,'r5_regulatory_contract')
    for module in (core,capture,observation,previous,observation.phases):
        file=str(Path(module.__file__).resolve());require(plan['sources'].get(file)==baseline.sha(file),'r5_reused_source')
    require(plan['sources'].get(str(Path(__file__).resolve()))==baseline.sha(__file__),'r5_worker_binding')
    return plan

def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--output-dir',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
    plan=load_plan(a.plan,a.plan_sha256)
    if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID_F367R5_REGULATORY_PROFILE',hardware_actions=False)));return 0
    require(os.environ.get('OM_F367_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==core.EVIDENCE_ROOT.resolve(),'owning_launcher_required')
    claim_once(plan,a.plan_sha256)
    return core.run(plan,a.output_dir,host_factory=Host,uart_factory=capture.Uart)
if __name__=='__main__':raise SystemExit(main())
