"""Combine prepared AP DFS policy with the exact R3 startup guard, offline only."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/kernel-port/f367'
R3=ROOT/'work/kernel-port/f366r3'
DEST=ROOT/'work/kernel-port/f367-r3-bootstrap'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def main():
 require(not DEST.exists(),'immutable F367 bootstrap source already exists');DEST.mkdir(parents=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(BASE/sub,DEST/sub)
 target='qdrv/qdrv/qdrv_control.c';shutil.copyfile(R3/target,DEST/target)
 pins={p.relative_to(DEST).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (DEST/sub).rglob('*') if p.is_file()}
 baseline={p.relative_to(BASE).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (BASE/sub).rglob('*') if p.is_file()}
 changed=sorted(n for n in pins if pins[n]!=baseline[n]);require(changed==[target],'unexpected F367 source delta')
 require('#define F367_NATIVE_AUTHORITY_BUILD 0' in (DEST/'kernel/f367_build_gate.h').read_text(),'authority must remain disabled')
 runtime=ROOT/'tools/f367_r3_bootstrap_contract.py'
 report={'schema':'openmitrastar.f367-r3-bootstrap-source/v1','status':'PREPARED_AUTHORITY_ZERO_NOT_A_FIRMWARE_IMAGE','source_pins':pins,'changed_from_f367':changed,'r3_control_exact':{'path':str(R3/target),'sha256':sha(R3/target)},'r3_runtime_template':{'path':str(runtime),'sha256':sha(runtime)},'f367_policy_unchanged':True,'provider_authority_compiled_off':True,'image_composition_allowed':False,'hardware_actions':False,'remaining_gates':['physical F366r3 acquisition and exact F365 return PASS','safe radar filter width20/context publication for operational52/20 after bootstrap36/80','bounded long watchdog and real health observer','AP DFS transition/client/CAC/NOP/RF qualification'],'notes':['The root-owned mission document and all R3 image/source seals are untouched.','The startup uses the original filter setter235/80 and exact cached guard; it does not enable DFS authority.']}
 (DEST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':str(DEST),'manifest_sha256':sha(DEST/'source-manifest.json'),'status':report['status']}))
if __name__=='__main__':main()
