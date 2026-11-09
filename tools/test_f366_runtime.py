"""Reuse actual F341 shell/IPC fixtures against F366 and real F365 startup donor."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,subprocess
from f366_runtime_contract import overlay,native_start
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/workspace/OpenMitraStar-build/f366/f366-components-20260922T093407Z/baseline-rootfs')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def literal(path,name):
 tree=ast.parse(path.read_text())
 return next(n.value.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets) and isinstance(n.value,ast.Constant))
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f366-runtime-'+stamp);out.mkdir(parents=True,exist_ok=False)
 helpers=out/'helpers';helpers.mkdir();contents=overlay()
 for name,data in contents.items():(helpers/Path(name).name).write_bytes(data)
 original=(BASE/'usr/sbin/om-radio5-start').read_bytes();module=BASE/'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'
 native=native_start(original,sha(module),'0'*64);(out/'native-start').write_bytes(native)
 harness=literal(ROOT/'tools/test_f341_runtime.py','harness').replace('F341','F366').replace('f341','f366').replace('schema=openmitrastar.f366-provider/v1','schema=openmitrastar.f341-provider/v1')
 harness=harness.replace("check('jobs_delta=20' in p.stdout and 'hardware_quiesced=0' in p.stdout)","check('jobs_delta=20' in p.stdout and 'hardware_quiesced=0' in p.stdout)\n check(sum(line.startswith('OMF366_STATUS index=') for line in p.stdout.splitlines())==20)")
 (out/'harness.py').write_bytes(harness.encode())
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py')],capture_output=True,text=True,timeout=40)
 (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
 result=json.loads(run.stdout) if not run.returncode else {'status':'FAIL','error':run.stderr[-4000:]}
 # The second fixture uses the actual canonical F340 protocol implementation
 # with explicitly fake watchdog and radio backends.
 ipcdir=out/'ipc';ipcdir.mkdir();(ipcdir/'helpers').mkdir()
 for name,data in contents.items():(ipcdir/'helpers'/Path(name).name).write_bytes(data)
 ipc=literal(ROOT/'tools/test_f341_f340_integration.py','test').replace('F341','F366').replace('f341','f366').replace('schema=openmitrastar.f366-provider/v1','schema=openmitrastar.f341-provider/v1')
 (ipcdir/'harness.py').write_bytes(ipc.encode());supervisor=ROOT/'outputs/kernel-port/f340-supervisor-20260921T133917Z/supervisor-test'
 irun=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ipcdir/'harness.py'),linux(supervisor)],capture_output=True,text=True,timeout=30)
 (ipcdir/'stdout').write_text(irun.stdout);(ipcdir/'stderr').write_text(irun.stderr)
 result['ipc']=json.loads(irun.stdout) if not irun.returncode else {'status':'FAIL','error':irun.stderr[-4000:]}
 result.update(schema='openmitrastar.f366-runtime-tests/v1',hardware_actions=False,helpers={name:hashlib.sha256(data).hexdigest() for name,data in contents.items()},native_donor_sha256=hashlib.sha256(original).hexdigest(),native_source_sha256=hashlib.sha256(native).hexdigest(),source_pins={str(ROOT/'tools/f366_runtime_contract.py'):sha(ROOT/'tools/f366_runtime_contract.py'),str(Path(__file__)):sha(Path(__file__))})
 if not run.returncode and not irun.returncode:result['status']='PASS_F366_RUNTIME_AND_ACTUAL_WATCHDOG_IPC'
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(run.returncode or irun.returncode)
if __name__=='__main__':raise SystemExit(main())
