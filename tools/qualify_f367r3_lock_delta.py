"""Bind the exact target probe and lock delta to reused R2 qualifications."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import f367r2_runtime_contract as old
import f367r3_runtime_contract as new
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
MANIFEST=DEVICE/'firmware/f367r2-f365-protected-preamble-device-bound/manifest.json'
RUNTIME=ROOT/'outputs/preflight/f367r2-runtime-20260922T134142Z/result.json'
DELTA=ROOT/'outputs/preflight/f367r3-owned-lock-20260922T143418Z/result.json'
LIVE=ROOT/'outputs/handoff-live/f367r3-lock-probe-20260922T143309Z/result.json'
PACKAGE=ROOT/'outputs/preflight/f367r3-lock-probe-20260922T143153Z/manifest.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):return {'path':str(p),'sha256':sha(p)}
def require(v,m):
 if not v:raise ValueError(m)
def main():
 require(sha(MANIFEST)=='c2ba47c911d135bfdfcfc317cac6182025a3f5fff13da0cbef9aed2360d1d659','sealed R2 manifest drift')
 m=json.loads(MANIFEST.read_text());baseline=json.loads(RUNTIME.read_text());delta=json.loads(DELTA.read_text());live=json.loads(LIVE.read_text());package=json.loads(PACKAGE.read_text())
 require(sha(LIVE)=='b211f67850e14413837f6a2c6ebc9292f139dceba7bae3d3cbf4f66f7f4f5ea5','exact live cleanup probe required')
 require(live['status']=='PASS' and live['exit_code']==0 and not live['stderr'] and live['radio_or_mtd_actions'] is False,'target cleanup did not pass')
 require(live['probe_sha256']==package['probe']['sha256']==sha(package['probe']['path']),'target probe package mismatch')
 require(delta['status']=='PASS_OWNED_LOCK_RELEASE_REAL_IPC_WITHOUT_RMDIR' and delta['path_has_rmdir'] is False,'delta IPC/ownership checks required')
 require(baseline['status']=='PASS_F367R2_SHELL_LIFECYCLE_AND_FAILURE_EOF','R2 runtime proof unavailable')
 for p,h in baseline['source_pins'].items():require(sha(p)==h,'reused runtime source drift')
 for record in (m['revision']['preamble_test'],m['revision']['guard_test']):require(sha(record['path'])==record['sha256'],'reused preamble/guard evidence drift')
 old_files=old.overlay();new_files=new.overlay();require(set(old_files)==set(new_files),'runtime file set changed')
 changed=[n for n in old_files if old_files[n]!=new_files[n]];require(changed==['usr/sbin/om-f367-stage'],'scope must be exactly stage lock delta')
 for n,b in old_files.items():require(hashlib.sha256(b).hexdigest()==baseline['helpers'][n],'R2 helper drift')
 before=old_files[changed[0]].decode();after=new_files[changed[0]].decode();anchor='token=$(cat "$state/token")'
 before_tail=before[before.index(anchor):];after_tail=after[after.index(anchor):]
 require(before_tail==after_tail,'IPC/phase/guard logic changed outside lock lifecycle')
 require(before[:before.index('i=0\n')]==after[:after.index('# The HGW')],'stage preconditions changed')
 start=after.index('release_lock()\n{');end=after.index('\nfinish_stage()\n{',start)
 require(hashlib.sha256(after[start:end].encode()).hexdigest()==package['exact_function_sha256'],'tested target cleanup differs from stage')
 new_hash=hashlib.sha256(new_files[changed[0]]).hexdigest();require(new_hash==package['stage']['sha256']==delta['stage_sha256'],'exact stage binding failed')
 helpers={n:hashlib.sha256(b).hexdigest() for n,b in new_files.items()}
 report={'schema':'openmitrastar.f367r3-lock-qualification/v1','status':'PASS_F367R3_OWNED_LOCK_WITH_REUSED_R2_RUNTIME','helpers':helpers,'source_pins':{str(new.OVERLAY/n):digest for n,digest in helpers.items()},'previous_stage_sha256':baseline['helpers'][changed[0]],'reused_runtime':item(RUNTIME),'reused_preamble':m['revision']['preamble_test'],'reused_guard':m['revision']['guard_test'],'delta_test':item(DELTA),'target_probe':item(LIVE),'probe_package':item(PACKAGE),'exact_cleanup_function_sha256':package['exact_function_sha256'],'changed_files':changed,'all_binary_artifacts_reused':True,'preamble_and_cac_nop_policy_unchanged':True,'hardware_actions_by_this_qualification':False}
 report['source_pins'][str(ROOT/'tools/f367r3_runtime_contract.py')]=sha(ROOT/'tools/f367r3_runtime_contract.py')
 out=ROOT/'outputs/preflight'/('f367r3-lock-qualified-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':report['status'],'stage_sha256':new_hash,'target_probe_sha256':sha(LIVE)},indent=2))
if __name__=='__main__':main()
