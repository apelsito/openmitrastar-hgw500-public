"""Build the GPL F338 kernel provider twice, without hardware or OEM objects."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f338'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=BASE/('f338-kernel-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 sources={}
 for lane in ('a','b'):
  for sub in ('kernel','uapi'):
   target=out/lane/sub;target.mkdir(parents=True)
   for p in (SOURCE/sub).iterdir():
    if p.is_file():(target/p.name).write_bytes(p.read_bytes());sources[str(p.relative_to(ROOT))]=sha(p)
 rows=[line for line in (ROOT/'work/linux510-radio-port/quantenna/Module.symvers').read_text().splitlines() if line.split()[1] in ('soc_shared_params','get_bootcfg_scancnt')]
 require(len(rows)==2,'platform exports absent');(out/'platform.symvers').write_bytes(('\n'.join(rows)+'\n').encode())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');qtn=linux(ROOT/'work/sources/Quantenna-GPL');compat=linux(ROOT/'work/linux510-radio-port/quantenna/qdrv/compat/include')
 pinned=ROOT/'outputs/kernel-port/f334-qdrv-profile-20260921T105936Z/kernel.config'
 digest=sha(pinned);require(digest=='cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e','pinned config hash drift')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src=/home/user/mitrastar-linux-5.10.260
kout=/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {digest}
'''
 script+=f'''for lane in a b; do
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/kernel" QTN_GPL={q(qtn)} QDRV_COMPAT={q(compat)} KBUILD_EXTRA_SYMBOLS="$out/platform.symvers" KCFLAGS="-ffile-prefix-map=$out/$lane=/f338-source" -j2 modules > "$out/build-$lane.log" 2>&1
 "${{tc}}nm" -u "$out/$lane/kernel/qtn_radar_f338.ko" > "$out/imports-$lane.txt"
done
cmp "$out/a/kernel/qtn_radar_f338.ko" "$out/b/kernel/qtn_radar_f338.ko"
cp "$kout/Module.symvers" "$out/kernel.symvers"
cp "$src/kernel/module.c" "$out/kernel-module.c"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 errors=[];artifact=None;module=out/'a/kernel/qtn_radar_f338.ko'
 if p.returncode:errors.append('kernel build failed')
 imports=[];export_audit=[]
 if module.exists():
  with module.open('rb') as f:
   elf=ELFFile(f);info=elf.get_section_by_name('.modinfo').data().decode(errors='replace').split('\0')
   require('license=GPL' in info,'provider license drift')
   imports=[s.name for s in elf.get_section_by_name('.symtab').iter_symbols() if s['st_shndx']=='SHN_UNDEF' and s.name]
  exports={}
  for path,owner in ((out/'kernel.symvers','GPL kernel'),(out/'platform.symvers','GPL platform')):
   if path.exists():
    for line in path.read_text().splitlines():
     bits=line.split();exports[bits[1]]={'symbol':bits[1],'owner':owner,'type':bits[3]}
  for name in imports:
   if name not in exports:errors.append('unresolved or unreviewed dependency '+name)
   else:export_audit.append(exports[name])
  if any(name.startswith(('f328_','f330_','f332_detect_')) for name in imports):errors.append('kernel still imports proprietary engine')
  artifact={'path':str(module),'bytes':module.stat().st_size,'sha256':sha(module),'modinfo':info}
 result={'schema':'openmitrastar.f338-kernel/v1','status':'PASS_OFFLINE_GPL_KERNEL_BUILD' if not errors else 'FAIL','errors':errors,'artifact':artifact,'sources':sources,'imports':imports,'export_license_audit':export_audit,'config_sha256':digest,'hardware':False,'loaded':False,'release_qualified':False,'reproducible':not errors}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':result['status'],'errors':errors,'artifact':artifact},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
