"""Actual F367 client/server processes with the existing fake watchdog backend."""
from pathlib import Path
import argparse,json,os,subprocess,tempfile,time
TOKEN='0123456789abcdef0123456789abcdef'
BOOT='01234567-89ab-cdef-0123-456789abcdef'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--binary',required=True);ap.add_argument('--result',type=Path,required=True);args=ap.parse_args();binary=str(Path(args.binary).resolve());passed=[]
 def case(name,fn):
  with tempfile.TemporaryDirectory(prefix='f367-ipc-') as folder:
   root=Path(folder);fixture=root/'fixture';state=root/'state';state.mkdir(mode=0o700)
   files={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/random/boot_id':BOOT,'/proc/sys/kernel/osrelease':'5.10.260-openmitrastar-radiohw','/proc/sys/kernel/version':'#358 @1790006400','/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'0000ffff'}
   for key,value in files.items():p=fixture/key.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value+'\n')
   env=dict(os.environ,F340_TEST_ROOT=str(fixture),F340_TEST_STATE=str(state),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='1000')
   server=subprocess.Popen([binary,'--session',TOKEN,'5400000'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   def cli(*cmd,ok=True,token=TOKEN):
    argv=[binary,'--status',token] if not cmd else [binary,'--request',token,*map(str,cmd)]
    p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=3);assert (p.returncode==0)==ok,(name,cmd,p.returncode,p.stdout,p.stderr)
    return json.loads(p.stdout) if p.stdout else None
   try:
    end=time.monotonic()+3
    while not (state/'supervisor.sock').exists():assert server.poll() is None and time.monotonic()<end;time.sleep(.01)
    fn(cli,server,env);passed.append(name)
   finally:
    if server.poll() is None:server.terminate()
    try:out,err=server.communicate(timeout=3)
    except subprocess.TimeoutExpired:server.kill();server.communicate();raise AssertionError('fake-server-containment')
    assert server.returncode==0,(name,server.returncode,out,err)
 def health_lease(cli,server,env):
  s=cli(1,'ARM');assert s['schema']=='openmitrastar.f367-supervisor-state/v1' and s['peer_verified'] and s['fd_held']
  s=cli(1,'BEGIN','quarantine',60000);phase=s['phase_deadline_monotonic_ms'];total=s['session_deadline_monotonic_ms'];health=s['health_deadline_monotonic_ms']
  time.sleep(.08);s=cli(1,'HEALTH','ok');assert s['health_deadline_monotonic_ms']>health and s['phase_deadline_monotonic_ms']==phase and s['session_deadline_monotonic_ms']==total
  cli(1,'CEASE',ok=False,token='a'*32);assert cli()['state']=='phase-active'
  time.sleep(5.15);s=cli();assert s['state']=='ceased-fd-held' and s['fd_held'];pets=s['pet_count'];time.sleep(.1);assert cli()['pet_count']==pets
 case('lease-expires-with-fd-held-no-renewed-phase-or-total',health_lease)
 def sequences(cli,server,env):
  cli(1,'ARM')
  for seq in range(1,130):
   if seq==129:cli(seq,'BEGIN','sequence',1000,ok=False);break
   cli(seq,'BEGIN','sequence',1000);cli(seq,'HEALTH','ok');cli(seq,'COMPLETE','sequence')
  assert cli()['state']=='ceased-fd-held'
 case('phase128-accepted-phase129-ceases',sequences)
 def owner_and_health_fail(cli,server,env):
  p=subprocess.run([binary,'--session',TOKEN,'5400000'],env=env,capture_output=True,timeout=3);assert p.returncode!=0
  cli(1,'ARM');cli(1,'BEGIN','bounded',60000);s=cli(1,'HEALTH','fail');assert s['state']=='ceased-fd-held' and s['fd_held']
 case('single-owner-and-explicit-health-failure',owner_and_health_fail)
 report=dict(schema='openmitrastar.f367-supervisor-ipc-tests/v1',passed=True,cases=passed,hardware_backend='F340_TEST_ONLY',hardware_actions=False)
 args.result.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0
if __name__=='__main__':raise SystemExit(main())
