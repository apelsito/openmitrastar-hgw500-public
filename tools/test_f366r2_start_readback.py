"""Run the actual native-start/readback block against asynchronous fake status."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f366r2_runtime_contract import native_start
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/workspace/OpenMitraStar-build/f366/f366-components-20260922T093407Z/baseline-rootfs')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f366r2-readback-'+stamp);out.mkdir(parents=True,exist_ok=False)
 source=native_start((BASE/'usr/sbin/om-radio5-start').read_bytes(),sha(BASE/'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'),'0'*64).decode()
 start=source.index("printf 'OMF366_NATIVE_START_ATTEMPT");end=source.index('/usr/sbin/om-f366-stage complete native-radar',start);end=source.index('\n',end)+1
 block=source[start:end].replace('/proc/openmitrastar_radar_f366/status','"$FIX/status"').replace('/usr/sbin/om-f366-stage','"$FIX/stage"')
 (out/'block.sh').write_bytes(('set -eu\nrefuse(){ printf "REFUSED %s\\n" "$1"; exit 31; }\ncontrol_set(){ [ "$1" = "radar enable eu" ] && [ "$2" = native-radar-enable ]; printf "called\\n" >>"$FIX/calls"; }\n'+block).encode())
 harness=r'''
from pathlib import Path
import os,subprocess,tempfile,json,sys
base=Path(sys.argv[1]);rows=[]
for name,started,jobs,advance,rc,reason in [('asynchronous-first-job',1,'0',True,0,''),('never-ready',1,'0',False,31,'f366-native-not-hardware-ready'),('invalid-jobs',1,'bad',True,31,'f366-native-invalid-jobs'),('never-started',0,'0',True,31,'f366-native-not-started')]:
 with tempfile.TemporaryDirectory(prefix='f366r2-readback-') as d:
  p=Path(d);(p/'status').write_text(f'started={started}\nhardware_dirty=1\nhardware_ready=0\nengine_fault_latched=0\ncallbacks=0\njobs_completed={jobs}\n')
  (p/'stage').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >>"$FIX/health"\n');(p/'stage').chmod(0o755)
  (p/'sleep').write_text('#!/bin/sh\nprintf "wait\\n" >>"$FIX/waits"\n'+('sed -i "s/hardware_ready=0/hardware_ready=1/;s/jobs_completed=0/jobs_completed=1/" "$FIX/status"\n' if advance else 'exit 0\n'));(p/'sleep').chmod(0o755)
  env=dict(os.environ,FIX=str(p),PATH=str(p)+':'+os.environ['PATH'])
  r=subprocess.run(['sh',str(base/'block.sh')],env=env,capture_output=True,text=True,timeout=5)
  assert r.returncode==rc and (not reason or reason in r.stdout),(name,r.returncode,r.stdout,r.stderr)
  assert (p/'calls').read_text().splitlines()==['called']
  waits=len((p/'waits').read_text().splitlines()) if (p/'waits').exists() else 0
  assert waits==({'asynchronous-first-job':1,'never-ready':5,'invalid-jobs':0,'never-started':0}[name]),(name,waits)
  rows.append(dict(case=name,passed=True,activation_count=1,waits=waits))
print(json.dumps(dict(status='PASS_ACTUAL_NATIVE_START_READBACK',cases=rows,hardware_actions=False)))
'''
 (out/'harness.py').write_bytes(harness.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py'),linux(out)],capture_output=True,text=True,timeout=30)
 result=json.loads(run.stdout) if not run.returncode else {'status':'FAIL','error':run.stderr[-3000:]}
 result.update(schema='openmitrastar.f366r2-start-readback-tests/v1',source_sha256=sha(ROOT/'tools/f366r2_runtime_contract.py'),actual_block_sha256=hashlib.sha256(block.encode()).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
