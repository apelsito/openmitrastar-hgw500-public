"""ARC build validation and native-source CLI tests only; no emulator or device."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--artifact-dir',type=Path,required=True);a=ap.parse_args();bundle=a.artifact_dir.resolve()
 assert (bundle/'build-pass.txt').read_text().strip()=='F344_BUILD_REPRODUCIBLE_NO_ARC_EXECUTION'
 artifacts=['wpa_supplicant','wpa_cli','libssl.a','libcrypto.a']
 assert all(sha(bundle/'a'/n)==sha(bundle/'b'/n) for n in artifacts)
 features=json.loads((bundle/'effective-feature-profile.json').read_text())
 assert all(x in features for x in ['CONFIG_DRIVER_MADWIFI=y','CONFIG_DRIVER_WEXT=y','CONFIG_TLS=openssl','CONFIG_CTRL_IFACE=y']) and 'CONFIG_DRIVER_NL80211=y' not in features
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f344-qualified-'+stamp);out.mkdir(parents=True)
 source=bundle/'source';original_main=(source/'wpa_supplicant/main.c').read_text();usage=original_main[original_main.index('static void usage(void)'):original_main.index('static void license(void)')]
 text=(source/'wpa_supplicant/wpa_supplicant.c').read_text();start=text.index('const char *wpa_supplicant_version =');decls=text[start:text.index('#ifndef CONFIG_NO_STDOUT_DEBUG',start)]
 drivers=[]
 for driver in ['wext','madwifi']:
  text=(source/f'src/drivers/driver_{driver}.c').read_text();text=text[text.index('const struct wpa_driver_ops wpa_driver_'+driver+'_ops'):]
  name=re.search(r'\.name\s*=\s*("[^"\n]+")',text)[1];desc=re.search(r'\.desc\s*=\s*("[^"\n]+")',text)[1]
  drivers.append(f'struct wpa_driver_ops {driver} = {{{name}, {desc}}};')
 renderer='#include <stdio.h>\n#include "version.h"\nstruct wpa_driver_ops {const char *name,*desc;};\n'+decls+'\n'+'\n'.join(drivers)+'\nstruct wpa_driver_ops *wpa_drivers[]={&wext,&madwifi,NULL};\n'+usage+'\nint main(void){usage();return 0;}\n'
 (out/'render_usage.c').write_bytes(renderer.encode())
 native='/home/user/openmitrastar-build/f344-native-cli-'+stamp;q=shlex.quote;vendor=ROOT/'work/sources/Quantenna-GPL/buildroot/package/wpa_supplicant'
 script=f'''set -eu
out={q(linux(out))}
native={q(native)}
test ! -e "$native"
mkdir "$native"
cp -a {q(linux(source))}/. "$native/"
python3 - {q(linux(bundle/'vendor.config'))} "$native/wpa_supplicant/.config" <<'PY'
from pathlib import Path
import sys,re
lines=Path(sys.argv[1]).read_text().splitlines();lines=[s for s in lines if not re.match(r'^(CFLAGS|LIBS(?:_[a-z])?)\\s*\\+?=',s)]
lines += ['CFLAGS += -std=gnu99 -Os -g0 -D_GNU_SOURCE -I{linux(ROOT/'work/sources/Quantenna-GPL/drivers/include/shared')} -I{linux(vendor/'madwifi')}', 'CFLAGS += -Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types -Wno-error=discarded-qualifiers']
Path(sys.argv[2]).write_text('\\n'.join(lines)+'\\n')
PY
make -C "$native/wpa_supplicant" clean > "$out/native-clean.log" 2>&1
make -C "$native/wpa_supplicant" -j4 wpa_cli CC=cc AR=ar PKG_CONFIG=/bin/false > "$out/native-build.log" 2>&1
cp "$native/wpa_supplicant/wpa_cli" "$out/wpa_cli.native-test-only"
"$out/wpa_cli.native-test-only" -h > "$out/wpa_cli-help.native.txt"
python3 {q(linux(ROOT/'tools/test_f344_cli_offline.py'))} --cli "$out/wpa_cli.native-test-only" --result "$out/cli-tests.json" > "$out/cli-tests.stdout" 2> "$out/cli-tests.stderr"
cc -std=c11 -O2 -Wall -Wextra -Werror -DCONFIG_DEBUG_SYSLOG -DEAP_TLS_OPENSSL -I{q(linux(source/'src/common'))} "$out/render_usage.c" -o "$out/render_usage"
"$out/render_usage" > "$out/wpa_supplicant-help.source-rendered.txt"
'''
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
 (out/'stdout.log').write_bytes(p.stdout);(out/'stderr.log').write_bytes(p.stderr)
 checks={'reproducible_arc_binaries_and_libraries':True,'original_vendor_features_preserved':True,'native_control_and_help':p.returncode==0,
  'repeater_option_parsed_and_stored':"case 'r':" in original_main and 'params.repeater_mode = 1;' in original_main,
  'help_before_supplicant_init':original_main.index("case 'h':")<original_main.index('wpa_supplicant_init(&params)')}
 for lane in ['a','b']:
  for name in ['wpa_supplicant','wpa_cli']:
   elf=(bundle/lane/(name+'.elf.txt')).read_text();dis=(bundle/lane/(name+'.disasm.txt')).read_text()
   checks[lane+'_'+name+'_arc_static_v4']='ARCompact' in elf and '0x403' in elf and 'Requesting program interpreter' not in elf and 'NEEDED' not in elf
   checks[lane+'_'+name+'_no_atomic']=not re.search(r'\b(?:llock|scond)\b',dis)
 if not p.returncode:
  help_text=(out/'wpa_supplicant-help.source-rendered.txt').read_text();checks['source_help_madwifi_repeater']='-r = run in repeater mode' in help_text and 'madwifi =' in help_text
 result={'schema':'openmitrastar.f344-qualified/v1','status':'PASS_OFFLINE_BUILD_AND_NATIVE_CONTROL' if all(checks.values()) else 'FAIL','checks':checks,
  'artifacts':{name:{'path':str(bundle/'a'/name),'bytes':(bundle/'a'/name).stat().st_size,'sha256':sha(bundle/'a'/name)} for name in artifacts},
  'native_cli_tests':json.loads((out/'cli-tests.json').read_text()) if (out/'cli-tests.json').exists() else None,
  'help_provenance':{'type':'native rendering of exact source usage(), with literal enabled driver metadata; not ARC execution','main_source_sha256':sha(source/'wpa_supplicant/main.c'),'usage_sha256':hashlib.sha256(usage.encode()).hexdigest()},
  'vendor_features':features,'arc_execution':'UNRUN: no compatible local Linux-user ARC700 decoder; no additional emulator attempts',
  'hardware_actions':False,'radio_or_wifi_acceptance':False,'real_interface_opened':False,'symvers':'N/A: userspace executables and static libraries',
  'limitations':['MADWIFI ignores scan params.freqs; actual driver channel mask is required','freq_list filters BSS selection but does not constrain RF scanning','STATUS has no frequency; use actual driver readback','OEM -r parse/store preserved; actual repeater topology is a separate driver operation','Check daemon reply text and state; CLI exit code alone is not acceptance']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'failed':[k for k,v in checks.items() if not v]},indent=2));return 0 if all(checks.values()) else 1
if __name__=='__main__':raise SystemExit(main())
