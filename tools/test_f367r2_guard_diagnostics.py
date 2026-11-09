"""Distinguish phase mismatch from expired HEALTH lease using actual IPCv2."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f367r2_runtime_contract import overlay
ROOT=Path(__file__).resolve().parents[1];SUP=ROOT/'outputs/kernel-port/f367-supervisor-20260922T115143Z/supervisor-test'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
HARNESS=r'''
from pathlib import Path
import json,os,subprocess,sys,tempfile,time
base=Path(sys.argv[1]);binary=sys.argv[2];stage=base/'stage';stage.write_text(stage.read_text().replace('#!/bin/ash\n','#!/bin/sh\n'));stage.chmod(0o755)
with tempfile.TemporaryDirectory(prefix='f367-guard-') as directory:
 root=Path(directory);fixture=root/'fixture';state=root/'state';state.mkdir(mode=0o700);owner=root/'owner';owner.mkdir(mode=0o700);token='f'*32
 fields={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/random/boot_id':'01234567-89ab-cdef-0123-456789abcdef','/proc/sys/kernel/osrelease':'5.10.260-openmitrastar-radiohw','/proc/sys/kernel/version':'#358 @1790006400','/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'00000000'}
 for n,v in fields.items():p=fixture/n.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v+'\n')
 for n,v in {'token':token,'sequence':'0','phase':'between-phases'}.items():(state/n).write_text(v+'\n')
 env=dict(os.environ,F340_TEST_ROOT=str(fixture),F340_TEST_STATE=str(owner),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='20000',OM_F367_STATE=str(state),OM_F367_WDT=binary)
 server=subprocess.Popen([binary,'--session',token,'5400000'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 def raw(*args):return subprocess.run([binary,'--request',token,*map(str,args)],env=env,capture_output=True,text=True,timeout=3)
 def inspect():return json.loads(subprocess.run([binary,'--status',token],env=env,capture_output=True,text=True,check=True,timeout=3).stdout)
 try:
  deadline=time.monotonic()+3
  while not(owner/'supervisor.sock').exists():assert time.monotonic()<deadline;time.sleep(.01)
  assert raw(1,'ARM').returncode==0
  assert subprocess.run(['sh',str(stage),'begin','preamble','30000'],env=env,capture_output=True,timeout=3).returncode==0
  before=inspect()
  wrong=subprocess.run(['sh',str(stage),'verify','module-load'],env=env,capture_output=True,text=True,timeout=3)
  after=inspect();assert wrong.returncode==25 and 'operation=phase-mismatch' in wrong.stderr and 'owner_state=phase-active' in wrong.stderr
  assert after['health_deadline_monotonic_ms']==before['health_deadline_monotonic_ms']
  time.sleep(5.3)
  expired=subprocess.run(['sh',str(stage),'verify','preamble'],env=env,capture_output=True,text=True,timeout=4)
  final=inspect();assert expired.returncode==24 and 'operation=HEALTH client_rc=1' in expired.stderr and 'owner_state=ceased-fd-held' in expired.stderr
  assert final['phase']=='preamble' and int(time.monotonic()*1000)<final['phase_deadline_monotonic_ms']
  print(json.dumps({'status':'PASS_DISTINCT_PHASE_AND_HEALTH_REJECTIONS','phase_mismatch':{'exit':wrong.returncode,'trace':wrong.stderr.strip()},'health_expired':{'exit':expired.returncode,'trace':expired.stderr.strip()},'phase_and_total_deadlines_unchanged':final['phase_deadline_monotonic_ms']==before['phase_deadline_monotonic_ms'] and final['session_deadline_monotonic_ms']==before['session_deadline_monotonic_ms'],'status_probe_renews_health':False,'hardware_actions':False}))
 finally:
  server.kill();server.wait(timeout=3)
'''
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367r2-guard-diagnostics-'+stamp);out.mkdir(parents=True,exist_ok=False)
 stage=overlay()['usr/sbin/om-f367-stage'];(out/'stage').write_bytes(stage);(out/'harness.py').write_bytes(HARNESS.encode())
 r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py'),linux(out),linux(SUP)],capture_output=True,text=True,timeout=25)
 result=json.loads(r.stdout) if not r.returncode else {'status':'FAIL','error':r.stderr[-4000:]};result.update(schema='openmitrastar.f367r2-guard-diagnostics/v1',stage_sha256=hashlib.sha256(stage).hexdigest(),supervisor_test_sha256=sha(SUP))
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return r.returncode
if __name__=='__main__':raise SystemExit(main())
