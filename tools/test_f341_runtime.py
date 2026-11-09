"""Offline shell transitions with a fake watchdog, fake proc files and no RF."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
from f341_runtime_contract import native_start
ROOT=Path(__file__).resolve().parents[1]
OVERLAY=ROOT/'versions/lyoko-foundation-6.10.1-f341-native-diagnostic/overlay'
def main():
 out=ROOT/'outputs/preflight'/('f341-runtime-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 helpers=out/'helpers';helpers.mkdir()
 for p in (OVERLAY/'usr/sbin').iterdir():(helpers/p.name).write_bytes(p.read_bytes())
 native=native_start((ROOT/'versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start').read_bytes());(out/'native-start').write_bytes(native)
 harness=r"""
from pathlib import Path
import json,os,subprocess,tempfile
base=Path(__file__).resolve().parent;helpers=base/'helpers';checks=0
def check(value):
 global checks
 checks+=1
 assert value,checks
for p in [*helpers.iterdir(),base/'native-start']:
 check(subprocess.run(['sh','-n',str(p)],capture_output=True).returncode==0)
for p in helpers.iterdir():
 p.write_text(p.read_text().replace('#!/bin/ash\n','#!/bin/sh\n',1));p.chmod(0o755)
with tempfile.TemporaryDirectory(prefix='f341-runtime-') as directory:
 root=Path(directory);state=root/'state';provider=root/'provider';provider.mkdir();fake=root/'bin';fake.mkdir();trace=root/'trace'
 env=dict(os.environ,OM_F341_STATE=str(state),OM_F341_PROVIDER=str(provider),OM_F341_STAGE=str(helpers/'om-f341-stage'),OM_F341_START=str(helpers/'om-radio5-start'),OM_F341_TRACE=str(trace),OM_F341_REAL_STATUS=str(helpers/'om-f341-status'))
 env['PATH']=str(fake)+':'+env['PATH']
 def put(name,text):
  p=fake/name;p.write_text(text);p.chmod(0o755);return p
 put('sleep','#!/bin/sh\nexit 0\n')
 wdt=put('wdt',r'''#!/bin/sh
printf '%s %s %s %s\n' "$1" "${3:-}" "${4:-}" "${5:-}" >>"$OM_F341_TRACE"
if [ "$1" = --request ] && [ "${4:-}" = ARM ] && [ "${OM_F341_DENY_ARM:-0}" = 1 ]; then exit 1; fi
printf '{"ack":true}\n'
''');env['OM_F341_WDT']=str(wdt)
 fake_native=put('native',r'''#!/bin/sh
set -eu
printf 'NATIVE_ENTER\n' >>"$OM_F341_TRACE"
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
pm_active=0
EOF
: >"$OM_F341_PROVIDER/control"
''');env['OM_F341_NATIVE']=str(fake_native)
 fake_status=put('status',r'''#!/bin/sh
set -eu
awk -F= 'BEGIN{OFS="="} $1=="jobs_completed" {$2=$2+1} {print}' "$OM_F341_PROVIDER/status" >"$OM_F341_PROVIDER/next"
mv "$OM_F341_PROVIDER/next" "$OM_F341_PROVIDER/status"
exec "$OM_F341_REAL_STATUS"
''');env['OM_F341_STATUS']=str(fake_status)
 def run(name,*args):return subprocess.run(['sh',str(helpers/name),*args],env=env,capture_output=True,text=True,timeout=8)
 p=run('om-radio5-start');check(p.returncode==0 and 'acquisition=0' in p.stdout and not trace.exists())
 p=run('om-radio5-start','--f341-native-diagnostic');check(p.returncode==31 and not trace.exists())
 p=run('om-f341-diagnostic','activate','INVALID');check(p.returncode==44 and not trace.exists())
 env['OM_F341_DENY_ARM']='1';p=run('om-f341-diagnostic','activate','f'*32);check(p.returncode==47 and 'NATIVE_ENTER' not in trace.read_text())
 import shutil
 shutil.rmtree(state);trace.unlink();env.pop('OM_F341_DENY_ARM')
 p=run('om-f341-diagnostic','activate','f'*32)
 assert p.returncode==0,(p.returncode,p.stdout,p.stderr,trace.read_text())
 check(p.returncode==0)
 lines=trace.read_text().splitlines();check(lines.index('--request 1 ARM ')<lines.index('--request 1 BEGIN module-load')<lines.index('NATIVE_ENTER'))
 check('--request 5 BEGIN pipeline-observe' in lines and lines[-1]=='--request 5 CEASE ')
 check((provider/'control').read_text()=='STOP_DIAGNOSTIC\n')
 check('jobs_delta=20' in p.stdout and 'hardware_quiesced=0' in p.stdout)
 before=trace.read_bytes();p=run('om-f341-diagnostic','activate','f'*32);check(p.returncode==45 and trace.read_bytes()==before)
 with (provider/'status').open('a') as f:f.write('raw_pulses=SHOULD_NOT_APPEAR\nmac=SHOULD_NOT_APPEAR\ncalibration=SHOULD_NOT_APPEAR\n')
 p=run('om-f341-status');check(p.returncode==0 and 'SHOULD_NOT_APPEAR' not in p.stdout and json.loads(p.stdout)['jobs_completed']==21)
 with (provider/'status').open('a') as f:f.write('jobs_completed=22\n')
 p=run('om-f341-status');check(p.returncode!=0 and not p.stdout)
 (provider/'status').unlink();p=run('om-f341-status');check(json.loads(p.stdout)['provider_present']==False)
 text=(base/'native-start').read_text()
 check(text.index('om-radar-engine-f341 --serve')<text.index('control_set start core-start'))
 check('hardware_enable=1 diagnostic_capture=1 authoritative_enable=0' in text)
 check('shadow_arm' not in text and 'OMRADIO5_ROLLBACK_ARMED' not in text)
 check(text.count('complete radio-nondfs')==1 and 'channel=36' in text)
print(json.dumps({'status':'PASS_OFFLINE_RUNTIME_TRANSITIONS','checks':checks,'watchdog':'FAKE','proc':'FAKE','hardware':False,'wifi_physical':'USER_DEFERRED'}))
"""
 # Embedded fixture strings use their normal newline bytes on the Linux side.
 (out/'harness.py').write_bytes(harness.encode())
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py')],capture_output=True,text=True,timeout=40)
 (out/'stdout').write_text(p.stdout);(out/'stderr').write_text(p.stderr)
 report=json.loads(p.stdout) if not p.returncode else {'status':'FAIL','error':p.stderr[-3500:]}
 report['sources']={str(p.relative_to(OVERLAY)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (OVERLAY/'usr/sbin').iterdir()};report['native_sha256']=hashlib.sha256(native).hexdigest()
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**report},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
