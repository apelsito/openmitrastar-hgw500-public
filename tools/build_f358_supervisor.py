"""Compile the existing supervisor with #358 profile; only changed-profile checks."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/versions/f358-supervisor'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 out=ROOT/'outputs/kernel-port'/('f358-supervisor-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);shutil.copytree(SOURCE,out/'source')
 assert sha(SOURCE/'f340_policy.h')=='93d5fb5c14b917e9535e3a91d364545772dffeb4828996a7db8dfa5f705b40fb'
 native='#define F340_TEST\n#include "source/f358_wdt_support.inc"\nint main(int argc,char**argv){int expected=argc==2&&atoi(argv[1]);int rc=arm();if(expected){if(rc||fake_opens!=1)return 1;device_close();}else if(!rc||fake_opens)return 2;puts("F358_PROFILE_PASS");return 0;}\n'
 (out/'profile.c').write_bytes(native.encode())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-function "$out/profile.c" -o "$out/profile"
for lane in a b; do
 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=c11 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-unused-function -pedantic -static -Wl,--gc-sections "$out/source/f358_supervisor.c" -o "$out/om-watchdog-supervisor-f358-$lane"
 "${{tc}}strip" --strip-unneeded "$out/om-watchdog-supervisor-f358-$lane"
done
cmp "$out/om-watchdog-supervisor-f358-a" "$out/om-watchdog-supervisor-f358-b"
'''
 (out/'build.sh').write_bytes(script.encode());r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True);(out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode(errors='replace')
 cases=[]
 for version in [358,350,340]:
  fixture=out/('fixture-'+str(version));files={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/osrelease':'5.10.260-openmitrastar-radiohw','/proc/sys/kernel/version':f'#{version} @1790006400','/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'0000ffff'}
  for name,value in files.items():p=fixture/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value+'\n')
  r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','env','F340_TEST_ROOT='+linux(fixture),linux(out/'profile'),str(int(version==358))],capture_output=True)
  cases.append({'version':version,'passed':r.returncode==0,'stdout':r.stdout.decode('ascii')});assert not r.returncode,cases[-1]
 artifact=out/'om-watchdog-supervisor-f358-a';assert b'#358 @1790006400' in artifact.read_bytes() and b'#350 @1790006400' not in artifact.read_bytes()
 result={'schema':'openmitrastar.f358-supervisor-build/v1','status':'PASS_OFFLINE_SUPERVISOR_PROFILE','hardware_actions':False,'artifact':{'path':str(artifact),'sha256':sha(artifact),'bytes':artifact.stat().st_size},'reproducible':True,'profile_tests':cases,'ipc_policy_unchanged_from_f356':True,'kernel_version':'#358 @1790006400','sources':{str(p):sha(p) for p in SOURCE.iterdir() if p.is_file()}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json')}))
if __name__=='__main__':main()
