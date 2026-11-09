"""Qualify revised shell lifecycle and failure EOF; radio/WDT backends are fake."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from test_f367_runtime import HARNESS as ORIGINAL,BASE,SUPERVISOR
from f367r2_runtime_contract import overlay,native_start
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367r2-runtime-'+stamp);out.mkdir(parents=True,exist_ok=False)
 for name,data in overlay().items():p=out/'helpers'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 native=native_start((BASE/'usr/sbin/om-radio5-start').read_bytes(),sha(BASE/'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'),'0'*64);(out/'native').write_bytes(native)
 sample=next(json.loads(x.split(' ',2)[2]) for x in (ROOT/'outputs/preflight/f367-functional-20260922T120620Z/stdout').read_text().splitlines() if x.startswith('SNAPSHOT initial '));(out/'kernel-example.json').write_text(json.dumps(sample)+'\n')
 harness=ORIGINAL.replace('"$OM_F367_STAGE" complete module-load\n','sleep 2\n"$OM_F367_STAGE" require-keeper preamble\n"$OM_F367_STAGE" complete preamble\n"$OM_F367_STAGE" begin module-load 30000\n"$OM_F367_STAGE" complete module-load\n',1).replace("in x])==6,p.stdout)","in x])==7,p.stdout)")
 harness=harness.replace("OM_F367_KERNEL_CONTROL=str(control),OM_F367_WDT=binary", "OM_F367_KERNEL_CONTROL=str(control),OM_F367_CONSOLE=str(root/'keeper-console'),OM_F367_WDT=binary")
 extra=r'''
  # A separately created fake boot fails before modules. The armed fake
  # supervisor remains alive10s, so an early EOF proves it kept no SSH pipes.
  failed_state=root/'failed-state';failed_owner=root/'failed-owner';failed_owner.mkdir(mode=0o700)
  failed_native=put('failed-native','#!/bin/sh\nexit 7\n')
  env2=dict(env,OM_F367_STATE=str(failed_state),F340_TEST_STATE=str(failed_owner),F340_TEST_HOLD_MS='10000',OM_F367_NATIVE=failed_native)
  started=time.monotonic();failed=subprocess.run(['sh',str(command),'activate','e'*32],env=env2,capture_output=True,text=True,timeout=6)
  check(failed.returncode==1 and 'OMF367_NATIVE_EXIT exit_code=7' in failed.stdout and 'OMF367_STOP' in failed.stdout,(failed.stdout,failed.stderr))
  check(time.monotonic()-started<5)
  pid=int((failed_state/'supervisor.pid').read_text());os.kill(pid,0);check(True)
  cmd=Path(f'/proc/{pid}/cmdline').read_bytes();check(binary.encode() in cmd);os.kill(pid,signal.SIGKILL)
'''
 harness=harness.replace(' finally:\n  for name in',extra+' finally:\n  for name in')
 harness=harness.replace("status='PASS_F367_ACTUAL_HELPERS_AND_V2_IPC'", "status='PASS_F367R2_SHELL_LIFECYCLE_AND_FAILURE_EOF'")
 (out/'harness.py').write_bytes(harness.encode());r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py'),linux(out),linux(SUPERVISOR)],capture_output=True,text=True,timeout=55)
 (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr);result=json.loads(r.stdout) if not r.returncode else {'status':'FAIL','error':r.stderr[-6000:]}
 result.update(schema='openmitrastar.f367r2-runtime-tests/v1',helpers={n:hashlib.sha256(b).hexdigest() for n,b in overlay().items()},source_pins={str(p):sha(p) for p in (Path(__file__),ROOT/'tools/f367r2_runtime_contract.py',ROOT/'tools/test_f367_runtime.py',SUPERVISOR)},native_sha256=hashlib.sha256(native).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return r.returncode
if __name__=='__main__':raise SystemExit(main())
