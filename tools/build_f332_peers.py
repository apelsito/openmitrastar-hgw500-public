"""Build wlan/platform peers coherently against the exact F321 kernel config.

Never replaces installed/current peer modules. Qdrv is excluded; its separate
F334-profile/F332-readiness lineage must be used by the final loader.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/linux510-radio-port/quantenna'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
FIRM=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=BASE/('f332-peers-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 inventory=json.loads((FIRM/'rootfs-inventory.json').read_text())['after'];installed={Path(n).name:v for n,v in inventory.items() if n.endswith('.ko')}
 copied={};snapshot=out/'source';snapshot.mkdir()
 for p in SOURCE.rglob('*'):
  if not p.is_file() or p.name.endswith('.mod.c'):continue
  rel=p.relative_to(SOURCE)
  keep=rel.parts[0] in ('wlan','platform') and (p.suffix in ('.c','.h','.S','.inc') or p.name=='Makefile')
  keep|=rel.parts[0]=='qdrv' and p.suffix in ('.h','.inc')
  if not keep:continue
  target=snapshot/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());copied[rel.as_posix()]=sha(p)
 (snapshot/'Makefile').write_bytes(b'subdir-ccflags-y += -DOPENMITRASTAR_QDRV_V89_PAIR=1 -DOPENMITRASTAR_SWITCH_EMAC_PORT=1 -DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1\nobj-m += wlan/ platform/\n')
 dependencies=[line for line in (SOURCE/'Module.symvers').read_text().splitlines() if '/qdrv/qdrv' in line.split()[2].replace('\\','/')]
 (out/'qdrv-exports.symvers').write_bytes(('\n'.join(dependencies)+'\n').encode())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src=/home/user/mitrastar-linux-5.10.260
kout=/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
cp "$kout/.config" "$out/kernel.config"
for lane in a b; do
 build=$(mktemp -d /home/user/openmitrastar-build/f332-peers-$lane-XXXXXXXX)
 printf '%s\\n' "$build" > "$out/build-$lane-directory.txt"
 cp -a "$out/source"/. "$build"/
 mkdir "$out/$lane"
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build" QTN_GPL={q(linux(ROOT/'work/sources/Quantenna-GPL'))} QDRV_COMPAT="$build/qdrv/compat/include" OPENMITRASTAR_QDRV_V89_PAIR=1 OPENMITRASTAR_SWITCH_EMAC_PORT=1 KBUILD_EXTRA_SYMBOLS="$out/qdrv-exports.symvers" KCFLAGS="-ffile-prefix-map=$build={linux(SOURCE)}" -j8 modules > "$out/build-$lane.log" 2>&1
 find "$build" -name '*.ko' -type f -exec cp -t "$out/$lane/" {{}} +
 cp "$build/Module.symvers" "$out/Module-$lane.symvers"
 find "$build" -name '*.o.cmd' -type f -exec grep -h -m1 '^cmd_' {{}} + > "$out/compile-$lane.txt"
done
for module in "$out/a/"*.ko; do cmp "$module" "$out/b/$(basename "$module")"; done
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','bash',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=900)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 errors=[];mods=[]
 if p.returncode:errors.append('peer build failed')
 else:
  for module in sorted((out/'a').glob('*.ko')):
   with module.open('rb') as f:
    info=ELFFile(f).get_section_by_name('.modinfo').data().decode(errors='replace').split('\0')
   if not any(s.startswith('vermagic=5.10.260-openmitrastar-radiohw') for s in info):errors.append('wrong vermagic '+module.name)
   row={'name':module.name,'bytes':module.stat().st_size,'sha256':sha(module),'same_as_f321':installed.get(module.name,{}).get('sha256')==sha(module),'f321_sha256':installed.get(module.name,{}).get('sha256'),'modinfo':info}
   mods.append(row)
  require(len(mods)>=15,'peer module list incomplete')
  for lane in ('a','b'):
   commands=[x for x in (out/('compile-'+lane+'.txt')).read_text().splitlines() if ' -c ' in x and '.mod.c' not in x]
   if not commands or not all(all(flag in x for flag in ('-DOPENMITRASTAR_QDRV_V89_PAIR=1','-DOPENMITRASTAR_SWITCH_EMAC_PORT=1','-DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1')) for x in commands):errors.append('incomplete peer profile flags')
 report={'schema':'openmitrastar.f332-coherent-peers/v1','status':'PASS_COHERENT_PEERS_OFFLINE' if not errors else 'FAIL','errors':errors,'kernel_config_sha256':sha(out/'kernel.config') if (out/'kernel.config').exists() else None,'sources':copied,'modules':mods,'reproducible':not errors,'qdrv_excluded':True,'source_existing_modules_replaced':False,'hardware':False,'firmware':False,'physical_abi_acceptance':False}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':report['status'],'errors':errors,'modules':len(mods)},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
