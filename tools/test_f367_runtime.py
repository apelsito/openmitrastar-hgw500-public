"""Run actual F367 helpers and actual v2 IPC with fake WDT/radio backends."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f367_runtime_contract import overlay,native_start
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/workspace/OpenMitraStar-build/f366/f366-components-20260922T093407Z/baseline-rootfs')
SUPERVISOR=ROOT/'outputs/kernel-port/f367-supervisor-20260922T115143Z/supervisor-test'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
HARNESS=r"""
from pathlib import Path
import json,os,signal,subprocess,sys,tempfile,time
base=Path(sys.argv[1]);binary=sys.argv[2];helpers=base/'helpers';checks=0
def check(x,msg=''):
 global checks
 checks+=1
 assert x,(checks,msg)
for p in helpers.rglob('*'):
 if p.is_file():
  check(subprocess.run(['sh','-n',str(p)],capture_output=True).returncode==0,str(p))
  p.write_text(p.read_text().replace('#!/bin/ash\n','#!/bin/sh\n',1));p.chmod(0o755)
check(subprocess.run(['sh','-n',str(base/'native')],capture_output=True).returncode==0)
with tempfile.TemporaryDirectory(prefix='f367-runtime-') as d:
 root=Path(d);fixture=root/'fixture';owner=root/'owner';owner.mkdir(mode=0o700);state=root/'state';provider=root/'provider';provider.mkdir();bin=root/'bin';bin.mkdir();trace=root/'trace';kernel=root/'kernel.json';control=root/'control'
 files={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/random/boot_id':'01234567-89ab-cdef-0123-456789abcdef','/proc/sys/kernel/osrelease':'5.10.260-openmitrastar-radiohw','/proc/sys/kernel/version':'#358 @1790006400','/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'00000000'}
 for name,value in files.items():p=fixture/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value+'\n')
 k=json.loads((base/'kernel-example.json').read_text());k.update(monotonic_ms=int(time.monotonic()*1000),quarantine_active=1,quarantine_remaining_ms=1800000,provider_channel=36,provider_bw=80,request_generation=7,filter_bw=80,phymode=13,region_es=1)
 kernel.write_text(json.dumps(k,separators=(',',':'))+'\n');control.write_text('')
 defaults={'schema':'openmitrastar.f341-provider/v1','started':1,'hardware_ready':1,'hardware_dirty':1,'ready':0,'callbacks':0,'jobs_completed':20,'job_timeouts':0,'protocol_errors':0,'hardware_errors':0,'engine_fault_latched':0,'last_error':0,'ipc_session':1,'ipc_sequence':20,'ipc_state':1,'service_closes':0,'postfilter_applied':1,'authority_build':1,'authoritative_enabled':1}
 (provider/'status').write_text(''.join(str(k)+'='+str(v)+'\n' for k,v in defaults.items()))
 def put(name,text):p=bin/name;p.write_text(text);p.chmod(0o755);return str(p)
 env=dict(os.environ,F340_TEST_ROOT=str(fixture),F340_TEST_STATE=str(owner),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='1000',OM_F367_STATE=str(state),OM_F367_PROVIDER=str(provider),OM_F367_KERNEL_STATE=str(kernel),OM_F367_KERNEL_CONTROL=str(control),OM_F367_WDT=binary,OM_F367_STAGE=str(helpers/'usr/sbin/om-f367-stage'),OM_F367_START=str(helpers/'usr/sbin/om-radio5-start'),OM_F367_KEEPER=str(helpers/'usr/sbin/om-f367-keeper'),OM_F367_COMMON=str(helpers/'usr/libexec/openmitrastar/f367-shell-common'),TRACE=str(trace),TEST_KERNEL=str(kernel),TEST_PROVIDER=str(provider),REAL_STATUS=str(helpers/'usr/sbin/om-f367-status'))
 status=put('status',r'''#!/usr/bin/python3
import json,os,time
from pathlib import Path
k=Path(os.environ['TEST_KERNEL']);d=json.loads(k.read_text());d['monotonic_ms']=int(time.monotonic()*1000);k.write_text(json.dumps(d,separators=(',',':'))+'\n')
p=Path(os.environ['TEST_PROVIDER'])/'status';rows=p.read_text().splitlines();rows=[x.split('=',1)[0]+'='+str(int(x.split('=',1)[1])+1) if x.startswith(('jobs_completed=','ipc_sequence=')) else x for x in rows];p.write_text('\n'.join(rows)+'\n')
os.execv(os.environ['REAL_STATUS'],[os.environ['REAL_STATUS']])
''');env['OM_F367_STATUS']=status
 native=put('native',r'''#!/bin/sh
set -eu
"$OM_F367_STAGE" complete module-load
"$OM_F367_STAGE" begin core-start 30000
sleep 6
"$OM_F367_STAGE" complete core-start
"$OM_F367_STAGE" begin vap-create 30000
"$OM_F367_STAGE" complete vap-create
"$OM_F367_STAGE" begin radio-nondfs 45000
"$OM_F367_STAGE" complete radio-nondfs
"$OM_F367_STAGE" begin native-radar 30000
"$OM_F367_STAGE" verify native-radar
"$OM_F367_STAGE" complete native-radar
''');env['OM_F367_NATIVE']=native
 iw=put('iw',r'''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:];trace=Path(os.environ['TRACE'])
with trace.open('a') as f:f.write(' '.join(args)+'\n')
if args[1]=='get_region':print('get_region:21317');sys.exit(0)
if args[1]=='get_mode':print('get_mode:11ac20');sys.exit(0)
assert Path(os.environ['OM_F367_KERNEL_CONTROL']).read_text().strip()=='PREPARE52'
if args[1]=='channel':
 p=Path(os.environ['TEST_KERNEL']);d=json.loads(p.read_text());d.update(channel=52,filter_bw=20,phymode=11,doth=1,tpc=1,quarantine_active=0,quarantine_remaining_ms=0,cac_active=1,cac_valid_continuity=1,cac_done=0,cac_remaining_ms=70000,tx_admission=0,generation=9,provider_channel=52,provider_bw=20);p.write_text(json.dumps(d,separators=(',',':'))+'\n')
 p=Path(os.environ['TEST_PROVIDER'])/'status';p.write_text(p.read_text().replace('ready=0\n','ready=1\n'))
''');env['OM_F367_IWPRIV']=iw;env['OM_F367_IWCONFIG']=iw
 command=helpers/'usr/sbin/om-f367-control'
 def run(*args,timeout=15):return subprocess.run(['sh',str(command),*args],env=env,capture_output=True,text=True,timeout=timeout)
 try:
  p=run('activate','f'*32,timeout=22);check(p.returncode==0,(p.stdout,p.stderr,(state/'keeper.log').read_text() if (state/'keeper.log').exists() else ''))
  check('OMF367_ACTIVATED' in p.stdout)
  check(len([x for x in p.stdout.splitlines() if 'command=begin' in x])==6,p.stdout)
  ack=json.loads((state/'arm-ack.json').read_text());check(ack['fd_held'] and ack['hardware_arm_confirmed'])
  time.sleep(1.2);s=run('status');check(s.returncode==0);j=json.loads(s.stdout);check(j['provider_started']==1 and j['provider_hardware_ready']==1 and j['provider_ready']==0)
  check(run('activate','f'*32).returncode==45)
  before=control.read_bytes();p=run('enter-dfs');check(p.returncode==16 and 'quarantine-active' in p.stdout and control.read_bytes()==before and not (state/'stopping').exists())
  d=json.loads(kernel.read_text());d.update(quarantine_active=0,quarantine_remaining_ms=0);kernel.write_text(json.dumps(d,separators=(',',':'))+'\n')
  p=run('enter-dfs');check(p.returncode==0,(p.stdout,p.stderr,(state/'keeper.log').read_text()));check(control.read_text()=='PREPARE52\n')
  calls=trace.read_text().splitlines();check(calls[:5]==['wifi0 doth 1','wifi0 tpc 1','wifi0 mode 11ac20','wifi0 radar_bw 20','wifi0 channel 52'],calls)
  d=json.loads(kernel.read_text());d.update(cac_active=0,cac_done=1,cac_remaining_ms=0,tx_admission=1);kernel.write_text(json.dumps(d,separators=(',',':'))+'\n')
  p=run('software-radar');check(p.returncode==0 and 'SOFTWARE_INJECTION' in p.stdout and control.read_text()=='RADAR\n',(p.stdout,p.stderr))
  d=json.loads(kernel.read_text());d.update(channel=36,nop_active=1,nop_remaining_ms=1800000,software_injections=1,cac_done=0,tx_admission=1);kernel.write_text(json.dumps(d,separators=(',',':'))+'\n')
  before=control.read_bytes();p=run('enter-dfs');check(p.returncode==16 and 'nop-active' in p.stdout and control.read_bytes()==before and not(state/'stopping').exists())
  p=run('stop');check(p.returncode==0 and control.read_text()=='ABORT\n');ack=json.loads((state/'last-ack.json').read_text());check(ack['state']=='ceased-fd-held' and ack['fd_held'])
 finally:
  for name in ('keeper.pid','supervisor.pid'):
   p=state/name
   if p.exists():
    try:
     pid=int(p.read_text());cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
     if str(helpers).encode() in cmd or binary.encode() in cmd:os.kill(pid,signal.SIGTERM)
    except (FileNotFoundError,ProcessLookupError):pass
print(json.dumps(dict(status='PASS_F367_ACTUAL_HELPERS_AND_V2_IPC',checks=checks,hardware_actions=False,watchdog_backend='F340_TEST_ONLY',radio_backend='FAKE',startup_health_kept_during_six_second_phase=True)))
"""
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367-runtime-'+stamp);out.mkdir(parents=True,exist_ok=False)
 for name,data in overlay().items():p=out/'helpers'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 native=native_start((BASE/'usr/sbin/om-radio5-start').read_bytes(),sha(BASE/'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'),'0'*64);(out/'native').write_bytes(native)
 sample=next(json.loads(line.split(' ',2)[2]) for line in (ROOT/'outputs/preflight/f367-functional-20260922T120620Z/stdout').read_text().splitlines() if line.startswith('SNAPSHOT initial '))
 (out/'kernel-example.json').write_text(json.dumps(sample)+'\n')
 (out/'harness.py').write_bytes(HARNESS.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py'),linux(out),linux(SUPERVISOR)],capture_output=True,text=True,timeout=55)
 (out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr)
 result=json.loads(run.stdout) if not run.returncode else {'status':'FAIL','error':run.stderr[-6000:]}
 result.update(schema='openmitrastar.f367-runtime-tests/v1',helpers={n:hashlib.sha256(b).hexdigest() for n,b in overlay().items()},source_pins={str(ROOT/'tools/f367_runtime_contract.py'):sha(ROOT/'tools/f367_runtime_contract.py'),str(Path(__file__)):sha(Path(__file__)),str(SUPERVISOR):sha(SUPERVISOR)},native_sha256=hashlib.sha256(native).hexdigest())
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
