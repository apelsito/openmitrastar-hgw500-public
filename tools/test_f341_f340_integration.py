"""Run actual F341 scripts with actual F340 IPC and its test-only WDT backend."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
OVERLAY=ROOT/'versions/lyoko-foundation-6.10.1-f341-native-diagnostic/overlay/usr/sbin'
SUPERVISOR=ROOT/'outputs/kernel-port/f340-supervisor-20260921T133917Z/supervisor-test'
def main():
 out=ROOT/'outputs/preflight'/('f341-f340-ipc-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 (out/'helpers').mkdir()
 for p in OVERLAY.iterdir():(out/'helpers'/p.name).write_bytes(p.read_bytes())
 test=r"""
from pathlib import Path
import json,os,signal,subprocess,sys,tempfile,time
base=Path(__file__).resolve().parent;binary=sys.argv[1];helpers=base/'helpers';token='a'*32
for p in helpers.iterdir():p.write_text(p.read_text().replace('#!/bin/ash\n','#!/bin/sh\n',1));p.chmod(0o755)
with tempfile.TemporaryDirectory(prefix='f341-f340-integration-') as directory:
 root=Path(directory);fixture=root/'fixture';wdtstate=root/'wdt';wdtstate.mkdir(mode=0o700);state=root/'f341';provider=root/'provider';provider.mkdir();bin=root/'bin';bin.mkdir()
 files={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/random/boot_id':'01234567-89ab-cdef-0123-456789abcdef','/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'00000000'}
 for path,text in files.items():p=fixture/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text+'\n')
 env=dict(os.environ,F340_TEST_ROOT=str(fixture),F340_TEST_STATE=str(wdtstate),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='1000',OM_F341_STATE=str(state),OM_F341_PROVIDER=str(provider),OM_F341_WDT=binary,OM_F341_STAGE=str(helpers/'om-f341-stage'),OM_F341_START=str(helpers/'om-radio5-start'),OM_F341_REAL_STATUS=str(helpers/'om-f341-status'))
 def put(name,text):p=bin/name;p.write_text(text);p.chmod(0o755);return str(p)
 put('sleep','#!/bin/sh\nexec /bin/sleep 0.02\n');env['PATH']=str(bin)+':'+env['PATH']
 env['OM_F341_NATIVE']=put('native',r'''#!/bin/sh
set -eu
"$OM_F341_STAGE" complete module-load
"$OM_F341_STAGE" begin core-start 30000
"$OM_F341_STAGE" complete core-start
"$OM_F341_STAGE" begin vap-create 30000
"$OM_F341_STAGE" complete vap-create
"$OM_F341_STAGE" begin radio-nondfs 45000
"$OM_F341_STAGE" complete radio-nondfs
cat >"$OM_F341_PROVIDER/status" <<EOF
schema=openmitrastar.f341-provider/v1
channel=36
callbacks=0
engine_fault_latched=0
job_timeouts=0
protocol_errors=0
hardware_errors=0
postfilter_applied=1
jobs_completed=1
EOF
: >"$OM_F341_PROVIDER/control"
''')
 env['OM_F341_STATUS']=put('status',r'''#!/bin/sh
set -eu
awk -F= 'BEGIN{OFS="="}$1=="jobs_completed"{$2=$2+1}{print}' "$OM_F341_PROVIDER/status" >"$OM_F341_PROVIDER/next"
mv "$OM_F341_PROVIDER/next" "$OM_F341_PROVIDER/status"
exec "$OM_F341_REAL_STATUS"
''')
 controller=subprocess.Popen(['sh',str(helpers/'om-f341-diagnostic'),'activate',token],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 try:
  stdout,stderr=controller.communicate(timeout=12);assert controller.returncode==0,(controller.returncode,stdout,stderr)
  armed=json.loads((state/'arm-ack.json').read_text());assert armed['fd_held'] and armed['hardware_arm_confirmed'] and armed['first_pet_confirmed'] and armed['peer_verified'] and armed['ack_sequence']==1 and armed['phase_sequence']==0
  ceased=json.loads((state/'last-ack.json').read_text());assert ceased['state']=='ceased-fd-held' and ceased['fd_held'] and ceased['phase_sequence']==5 and ceased['peer_verified']
  assert (provider/'control').read_text()=='STOP_DIAGNOSTIC\n'
  assert 'jobs_delta=20' in stdout and 'hardware_quiesced=0' in stdout
  end=time.monotonic()+3
  while (wdtstate/'supervisor.sock').exists():assert time.monotonic()<end;time.sleep(.02)
 finally:
  try:os.killpg(controller.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  if controller.poll() is None:controller.wait(timeout=3)
 print(json.dumps({'status':'PASS_F341_F340_ACTUAL_IPC','arm_ack_verified':True,'phase_sequences':[1,2,3,4,5],'cease_fd_held':True,'controller_observations':20,'no_hardware_quiesce_claim':True,'hardware_backend':'F340_TEST_ONLY','radio_backend':'FAKE','hardware_actions':False,'wifi_physical':'USER_DEFERRED'}))
"""
 (out/'harness.py').write_bytes(test.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py'),linux(SUPERVISOR)],capture_output=True,text=True,timeout=30)
 (out/'stdout').write_text(p.stdout);(out/'stderr').write_text(p.stderr)
 result=json.loads(p.stdout) if not p.returncode else {'status':'FAIL','error':p.stderr[-4000:]};result['supervisor_test_sha256']=hashlib.sha256(SUPERVISOR.read_bytes()).hexdigest();result['sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OVERLAY.iterdir()}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
