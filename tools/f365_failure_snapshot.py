"""Best-effort local evidence; this function must never obstruct recovery."""
import json,os
def save_failure_snapshot(out,result):
 try:
  final=out/'failure-before-recovery.json';temporary=out/'failure-before-recovery.json.tmp'
  data={**result,'snapshot_schema':'openmitrastar.f365-failure-before-recovery/v1','snapshot_phase':'before-any-recovery-action'}
  temporary.write_text(json.dumps(data,indent=2)+'\n',encoding='ascii');os.replace(temporary,final)
  return True
 except Exception as error:
  result['failure_snapshot_error']=type(error).__name__
  return False
