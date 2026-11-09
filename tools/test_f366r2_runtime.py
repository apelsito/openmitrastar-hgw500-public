"""Reuse actual F341 shell/IPC fixtures against F366 and real F365 startup donor."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,subprocess
from f366r2_runtime_contract import overlay,native_start
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/workspace/OpenMitraStar-build/f366/f366-components-20260922T093407Z/baseline-rootfs')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def literal(path,name):
 tree=ast.parse(path.read_text())
 return next(n.value.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets) and isinstance(n.value,ast.Constant))
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f366r2-runtime-'+stamp);out.mkdir(parents=True,exist_ok=False)
 helpers=out/'helpers';helpers.mkdir();contents=overlay()
 for name,data in contents.items():(helpers/Path(name).name).write_bytes(data)
 original=(BASE/'usr/sbin/om-radio5-start').read_bytes();module=BASE/'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'
 native=native_start(original,sha(module),'0'*64);(out/'native-start').write_bytes(native)
 harness=literal(ROOT/'tools/test_f341_runtime.py','harness').replace('F341','F366').replace('f341','f366').replace('schema=openmitrastar.f366-provider/v1','schema=openmitrastar.f341-provider/v1')
 harness=harness.replace("check('jobs_delta=20' in p.stdout and 'hardware_quiesced=0' in p.stdout)","check('jobs_delta=20' in p.stdout and 'hardware_quiesced=0' in p.stdout)\n check(sum(line.startswith('OMF366_STATUS index=') for line in p.stdout.splitlines())==20)")
 harness=harness.replace('schema=openmitrastar.f341-provider/v1\n','schema=openmitrastar.f341-provider/v1\nstarted=1\nhardware_dirty=1\n')
 harness=harness.replace('"$OM_F366_STAGE" complete radio-nondfs\n','"$OM_F366_STAGE" complete radio-nondfs\n"$OM_F366_STAGE" begin native-radar 30000\n"$OM_F366_STAGE" complete native-radar\n')
 harness=harness.replace('--request 5 BEGIN pipeline-observe','--request 6 BEGIN pipeline-observe').replace('--request 5 CEASE','--request 6 CEASE')
 regression=""" import shutil
 shutil.rmtree(state);trace.unlink()
 saved_native=fake_native.read_text();saved_status=(provider/'status').read_bytes();fake_native.write_text(saved_native.replace('started=1','started=0'))
 p=run('om-f366-diagnostic','activate','f'*32)
 check(p.returncode==58 and 'reason=native-not-started' in p.stdout and 'OMF366_STATUS index=' not in p.stdout)
 fake_native.write_text(saved_native);(provider/'status').write_bytes(saved_status)
"""
 harness=harness.replace(' before=trace.read_bytes();p=run(',regression+' before=trace.read_bytes();p=run(')
 harness=harness.replace(" check(text.count('complete radio-nondfs')==1 and 'channel=36' in text)"," check(text.count('complete radio-nondfs')==1 and 'channel=36' in text)\n check(text.index('verify native-radar')<text.index(\"control_set 'radar enable eu'\")<text.index(\"grep -qx 'started=1'\"))\n check(text.count('openmitrastar_native_radar_diagnostic=1')==3)")
 (out/'harness.py').write_bytes(harness.encode())
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py')],capture_output=True,text=True,timeout=40)
 (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
 result=json.loads(run.stdout) if not run.returncode else {'status':'FAIL','error':run.stderr[-4000:]}
 # The second fixture uses the actual canonical F340 protocol implementation
 # with explicitly fake watchdog and radio backends.
 ipcdir=out/'ipc';ipcdir.mkdir();(ipcdir/'helpers').mkdir()
 for name,data in contents.items():(ipcdir/'helpers'/Path(name).name).write_bytes(data)
 ipc=literal(ROOT/'tools/test_f341_f340_integration.py','test').replace('F341','F366').replace('f341','f366').replace('schema=openmitrastar.f366-provider/v1','schema=openmitrastar.f341-provider/v1')
 ipc=ipc.replace('schema=openmitrastar.f341-provider/v1\n','schema=openmitrastar.f341-provider/v1\nstarted=1\nhardware_dirty=1\n')
 ipc=ipc.replace('"$OM_F366_STAGE" complete radio-nondfs\n','"$OM_F366_STAGE" complete radio-nondfs\n"$OM_F366_STAGE" begin native-radar 30000\n"$OM_F366_STAGE" complete native-radar\n')
 ipc=ipc.replace("['phase_sequence']==5","['phase_sequence']==6").replace("'phase_sequences':[1,2,3,4,5]","'phase_sequences':[1,2,3,4,5,6]")
 (ipcdir/'harness.py').write_bytes(ipc.encode());supervisor=ROOT/'outputs/kernel-port/f340-supervisor-20260921T133917Z/supervisor-test'
 irun=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ipcdir/'harness.py'),linux(supervisor)],capture_output=True,text=True,timeout=30)
 (ipcdir/'stdout').write_text(irun.stdout);(ipcdir/'stderr').write_text(irun.stderr)
 result['ipc']=json.loads(irun.stdout) if not irun.returncode else {'status':'FAIL','error':irun.stderr[-4000:]}
 result.update(schema='openmitrastar.f366r2-runtime-tests/v1',hardware_actions=False,helpers={name:hashlib.sha256(data).hexdigest() for name,data in contents.items()},native_donor_sha256=hashlib.sha256(original).hexdigest(),native_source_sha256=hashlib.sha256(native).hexdigest(),source_pins={str(ROOT/'tools/f366r2_runtime_contract.py'):sha(ROOT/'tools/f366r2_runtime_contract.py'),str(Path(__file__)):sha(Path(__file__))})
 result['source_pins'][str(ROOT/'tools/f366_runtime_contract.py')]=sha(ROOT/'tools/f366_runtime_contract.py')
 if not run.returncode and not irun.returncode:result['status']='PASS_F366R2_RUNTIME_AND_ACTUAL_WATCHDOG_IPC'
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(run.returncode or irun.returncode)
if __name__=='__main__':raise SystemExit(main())
