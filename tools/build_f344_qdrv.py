"""Build the opt-in AP/STA/repeater qdrv extension against F340, offline."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,shutil,subprocess
import f334_qdrv_contract as elf
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/linux510-radio-port/quantenna-f344-modes'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
F341=BASE/'f341-closure-20260921T134402Z'
PROVIDER=BASE/'f338-kernel-20260921T131909Z/a/kernel/Module.symvers'
KERNEL='/home/user/openmitrastar-build/f340-watchdog-20260921T132951Z/linux'
KOUT='/home/user/openmitrastar-build/f341-module-context-20260921T134402Z'
CONFIG_SHA='f374913b8d2adc7c4138af32263b650eeb967b4defc0139cfd00e6bff7ba1118'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/kernel-port'/('f344-qdrv-modes-'+stamp);out.mkdir(parents=True,exist_ok=False)
 shutil.copytree(SOURCE,out/'source')
 baseline=elf.inspect(Path(json.loads((F341/'manifest.json').read_text())['modules']['qdrv']['path']))
 rows=(F341/'a/peers/Module.symvers').read_text()+PROVIDER.read_text();(out/'dependencies.symvers').write_bytes(rows.encode())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src={q(KERNEL)}
kout={q(KOUT)}
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {CONFIG_SHA}
for lane in a b; do
 build=/home/user/openmitrastar-build/f344-qdrv-{stamp}-$lane
 test ! -e "$build"
 mkdir "$build"
 cp -a "$out/source"/. "$build"/
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f344-modes KBUILD_BUILD_VERSION=344 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build" QTN_GPL={q(linux(ROOT/'work/sources/Quantenna-GPL'))} QDRV_COMPAT="$build/qdrv/compat/include" OPENMITRASTAR_QDRV_V89_PAIR=1 OPENMITRASTAR_SWITCH_EMAC_PORT=1 KBUILD_EXTRA_SYMBOLS="$out/dependencies.symvers" KCFLAGS="-ffile-prefix-map=$build=/f344-source" -j4 modules > "$out/build-$lane.log" 2>&1
 cp "$build/qdrv/qdrv.ko" "$out/qdrv-$lane.ko"
 cp "$build/Module.symvers" "$out/Module-$lane.symvers"
done
cmp "$out/qdrv-a.ko" "$out/qdrv-b.ko"
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware':False}),flush=True)
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr);errors=[];artifact=None
 if p.returncode:errors.append('qdrv build failed')
 else:
  artifact=elf.inspect(out/'qdrv-a.ko');expected={**baseline['parameters'],'openmitrastar_mode_workflow':0o400}
  if artifact['parameters']!=expected:errors.append('parameter profile drift beyond new opt-in flag')
  if artifact['functions']!=baseline['functions']:errors.append('beacon preflight profile changed')
  if 'license=GPL' not in artifact['modinfo']:errors.append('GPL module license changed')
  if not any(line.startswith('depends=') and 'qtn_radar_f338' in line for line in artifact['modinfo']):errors.append('wrong radar provider dependency')
 result={'schema':'openmitrastar.f344-qdrv-modes/v1','status':'PASS_OFFLINE_MODE_QDRV_BUILD' if not errors else 'FAIL','errors':errors,'artifact':{'path':str(out/'qdrv-a.ko'),'bytes':artifact['bytes'],'sha256':artifact['sha256']} if artifact else None,'parameter_profile':artifact['parameters'] if artifact else None,'kernel_config_sha256':CONFIG_SHA,'reproducible':not errors,'hardware':False,'wifi_physical':'USER_DEFERRED','new_gate_default':False,'sources':{str(p.relative_to(out/'source')):sha(p) for p in (out/'source').rglob('*') if p.is_file()}}
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'manifest':str(out/'manifest.json'),'status':result['status'],'errors':errors,'artifact':result['artifact']},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
