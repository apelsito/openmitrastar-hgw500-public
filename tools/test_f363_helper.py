"""Exercise the F363 helper with fake sysfs and an explicit fake loader."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/versions/f363-temperature-diagnostic/overlay/usr/sbin/om-temperature-f363'
def main():
 out=Path('/workspace/OpenMitraStar-build/f363')/('f363-helper-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 (out/'production-helper').write_bytes(SRC.read_bytes())
 harness=r'''
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
base=Path(__file__).resolve().parent;checks=0
def check(v):
 global checks
 checks+=1
 assert v,checks
with tempfile.TemporaryDirectory(prefix='f363-helper-') as directory:
 root=Path(directory);sys=root/'sys';bin=root/'bin';bin.mkdir();modules=root/'modules';modules.mkdir();trace=root/'trace';catalog=root/'catalog'
 for n in ('hwmon.ko','temp_sens.ko'):(modules/n).write_bytes(b'fake module '+n.encode())
 loader=bin/'loader';loader.write_text('#!/bin/sh\nprintf "%s|%s\\n" "$1" "${2-unset}" >>"'+str(trace)+'"\nname=${1##*/}; name=${name%.ko}; mkdir -p "'+str(sys)+'/module/$name"\nif [ "$name" = temp_sens ]; then\n mkdir -p "'+str(sys)+'/class/hwmon/hwmon7"\n printf "363\\n" >"'+str(sys)+'/module/temp_sens/version"\n printf "topaz_internal\\n" >"'+str(sys)+'/class/hwmon/hwmon7/name"\n for n in enabled activation_attempted; do printf "0\\n" >"'+str(sys)+'/class/hwmon/hwmon7/$n"; done\n printf "%s\\n" -19 >"'+str(sys)+'/class/hwmon/hwmon7/activation_error"\nfi\n');loader.chmod(0o755)
 cat=bin/'cat';cat.write_text('#!/bin/sh\nprintf "CAT:%s\\n" "$1" >>"'+str(trace)+'"\nexec /bin/cat "$@"\n');cat.chmod(0o755)
 catalog.write_text(''.join(hashlib.sha256((modules/n).read_bytes()).hexdigest()+'  '+str(modules/n)+'\n' for n in ('hwmon.ko','temp_sens.ko')))
 source=(base/'production-helper').read_text();source=source.replace('#!/bin/ash','#!/bin/sh').replace('PATH=/sbin:/bin:/usr/sbin:/usr/bin','PATH='+str(bin)+':/sbin:/bin:/usr/sbin:/usr/bin').replace('/sys/',str(sys)+'/').replace('catalog=/usr/share/openmitrastar/temperature/artifacts.sha256','catalog='+str(catalog)).replace('modules=/lib/modules/$(uname -r)/openmitrastar/radio5g','modules='+str(modules)).replace('loader=/usr/sbin/ram-insmod-qtn','loader='+str(loader)).replace('8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6',hashlib.sha256(loader.read_bytes()).hexdigest())
 helper=root/'helper';helper.write_text(source);helper.chmod(0o755)
 def run(action):return subprocess.run(['sh',str(helper),action],capture_output=True,text=True,timeout=3)
 check(run('status').returncode!=0)
 p=run('load');check(p.returncode==0 and 'enabled=0' in p.stdout and 'activation_error=-19' in p.stdout)
 sensor=sys/'class/hwmon/hwmon7';(sensor/'temp1_input').write_text('25000\n');(sensor/'experimental_enable').write_text('')
 traces=trace.read_text();check(str(modules/'hwmon.ko')+'|' in traces and str(modules/'temp_sens.ko')+'|' in traces and 'unset' not in traces)
 trace.write_text('');check(run('status').returncode==0);check('temp1_input' not in trace.read_text() and 'experimental_enable' not in trace.read_text())
 check(run('require-module').returncode==0)
 check(run('enable').returncode==0 and (sensor/'experimental_enable').read_text()=='1\n')
 check(run('read').stdout=='25000\n')
 (sys/'module/temp_sens/version').write_text('old\n');check(run('require-module').returncode!=0);(sys/'module/temp_sens/version').write_text('363\n')
 duplicate=sys/'class/hwmon/hwmon8';duplicate.mkdir();(duplicate/'name').write_text('topaz_internal\n');check(run('status').returncode!=0)
 check(run('invalid').returncode==64)
print(json.dumps({'passed':True,'checks':checks,'fake_sysfs':True,'fake_loader':True,'hardware_actions':False}))
'''
 (out/'harness.py').write_bytes(harness.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3','-B',linux(out/'harness.py')],capture_output=True,text=True,timeout=30)
 result={'status':'PASS_F363_HELPER_FAKE_SYSFS' if not p.returncode else 'FAIL','stdout':p.stdout,'stderr':p.stderr,'production_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'hardware_actions':False};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
