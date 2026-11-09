"""One capture-only repeat of the exact F367 image using the unchanged core."""
from pathlib import Path
import argparse,json,os
import f367_campaign_executor as core
import f367_uart_capture_r2 as capture

IMAGE_SHA='447f94aa1be95b1ba52a47d206978bc8a359e3c57e7435d475a3e49b9cb28aa0'

def load_plan(path,digest):
 plan=core.load_plan(path,digest)
 core.require(plan.get('uart_semantic_capture_revision')==2 and plan.get('repeat_scope')=='one-same-image-capture-only-repeat' and plan.get('max_completed_executions')==1,'capture_repeat_scope')
 core.require(plan['images']['f367']['sha256']==IMAGE_SHA and plan['images']['f367']['bytes']==5455872 and plan['images']['f367']['full_slot_crc32']=='6f77010f','unchanged_f367_required')
 for module in (core,capture):
  source=str(Path(module.__file__).resolve());core.require(plan['sources'].get(source)==core.baseline.sha(source),'capture_repeat_source')
 core.require(plan['sources'].get(str(Path(__file__).resolve()))==core.baseline.sha(__file__),'capture_worker_not_bound')
 return plan

def claim_once(plan,digest):
 """Owner launcher has already taken the hardware lease before this claim."""
 directory=core.EVIDENCE_ROOT/'one-shot-plans'
 directory.mkdir(parents=True,exist_ok=True)
 core.require(not directory.is_symlink() and not getattr(directory,'is_junction',lambda:False)(),'one_shot_directory_reparse')
 path=directory/(digest+'.json')
 # A failed execution consumes this exact plan too; retry needs a new plan.
 with path.open('x',encoding='ascii') as stream:
  stream.write(json.dumps(dict(plan_sha256=digest,scope=plan['repeat_scope']))+'\n')
 return str(path)

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--output-dir',type=Path);p.add_argument('--execute',action='store_true');args=p.parse_args()
 plan=load_plan(args.plan,args.plan_sha256)
 if not args.execute:
  print(json.dumps(dict(status='OFFLINE_VALID_F367_CAPTURE_R2',hardware_actions=False,unchanged_image=IMAGE_SHA)));return 0
 core.require(os.environ.get('OM_F367_CONTEXT') and args.output_dir and args.output_dir.is_dir() and args.output_dir.resolve().parent==core.EVIDENCE_ROOT.resolve(),'owning_launcher_required')
 claim_once(plan,args.plan_sha256)
 # Same writer, campaign, deadlines, recovery and acceptance. Only UART class differs.
 return core.run(plan,args.output_dir,uart_factory=capture.Uart)

if __name__=='__main__':raise SystemExit(main())
