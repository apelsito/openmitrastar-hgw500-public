"""Build a disabled F332 kernel bundle; never load modules or contact hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shlex,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f332_dfs_provider'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
PIPE=BASE/'f332-pipeline-20260921T115620Z'
CAP=BASE/'f332-capacity-20260921T104538Z'
PRE=BASE/'f330-kernel-preprocess-20260921T103900Z'
POST=BASE/'f331-kernel-20260921T103722Z'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--f333-result',type=Path);args=ap.parse_args()
 pipeline=json.loads((PIPE/'result.json').read_text());require(pipeline['status']=='PASS_OEM_PIPELINE_QEMU','pipeline unqualified')
 for rel in ('engine/f332_detector_core.c','engine/f332_detector.h','provider/f332_pipeline.c','provider/f332_pipeline.h'):
  key=str((SOURCE/rel).relative_to(ROOT));require(sha(SOURCE/rel)==pipeline['sources'][key],'pipeline source drift '+rel)
 cap=json.loads((CAP/'result.json').read_text());require(cap['status']=='PASS_OEM_CAPACITY256_TIMESTAMP32','capacity unqualified')
 capture_qualified=False
 if args.f333_result:
  capture=json.loads(args.f333_result.read_text());capture_qualified=capture.get('status')=='PASS_PORTABLE_DECODER_VS_ORIGINAL_QEMU_LOOPS' and capture.get('comparisons')==[2368,320,52870,1756160,0,0]
  require(capture_qualified,'F333 oracle not PASS')
  for name in ('f333_acquisition.c','f333_acquisition.h'):
   require(sha(ROOT/'work/kernel-port/modules/f333_acquisition'/name)==capture['sources'][name],'F333 source/oracle drift')
 for base_dir,expected in ((PRE,'b566b28a7e6da502497afc40a1d4c5e8ca005135dd3c0aa82650f9b728e19a58'),(POST,'a73a10ed48e35f888b12566e5bacbc17e3a215cb53d42f8dc54e484075424d74')):
  proof=json.loads((base_dir/'result.json').read_text());require(proof['module']['sha256']==expected and sha(Path(proof['module']['path']))==expected,'engine dependency artifact drift')
 out=BASE/('f332-kernel-bundle-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 sources={}
 for lane in ('a','b'):
  for sub in ('engine','provider'):
   target=out/lane/sub;target.mkdir(parents=True)
   for p in (SOURCE/sub).iterdir():
    if p.is_file():(target/p.name).write_bytes(p.read_bytes());sources[str(p.relative_to(ROOT))]=sha(p)
  for n in ('f328-oem-classifier.o','eu-profile.h'):
   require(sha(CAP/n)==cap['artifacts'][n]['sha256'],'OEM input drift');(out/lane/'engine'/n).write_bytes((CAP/n).read_bytes())
  for n in ('f333_acquisition.c','f333_acquisition.h'):
   p=ROOT/'work/kernel-port/modules/f333_acquisition'/n;(out/lane/'provider'/n).write_bytes(p.read_bytes());sources[str(p.relative_to(ROOT))]=sha(p)
  for old,new in ((PRE/'a/Module.symvers','preprocess.symvers'),(POST/'a/Module.symvers','postfilter.symvers')):(out/lane/new).write_bytes(old.read_bytes())
 platform=ROOT/'work/linux510-radio-port/quantenna/Module.symvers'
 rows=[line for line in platform.read_text().splitlines() if line.split()[1] in ('soc_shared_params','get_bootcfg_scancnt')];require(len(rows)==2,'platform owner exports ambiguous')
 (out/'platform.symvers').write_bytes(('\n'.join(rows)+'\n').encode())
 (out/'test_f332_events.c').write_bytes((SOURCE/'tests/test_f332_events.c').read_bytes())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');qtn=linux(ROOT/'work/sources/Quantenna-GPL');compat=linux(ROOT/'work/linux510-radio-port/quantenna/qdrv/compat/include')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src=/home/user/mitrastar-linux-5.10.260
kout=/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I"$out/a/provider" -I"$out/a/engine" "$out/a/provider/f332_events.c" "$out/test_f332_events.c" -o "$out/test-events"
"$out/test-events" > "$out/event-tests.txt"
for lane in a b; do
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/engine" KCFLAGS="-ffile-prefix-map=$out/$lane=/f332-source" -j2 modules > "$out/engine-$lane.log" 2>&1
 cat "$out/platform.symvers" "$out/$lane/preprocess.symvers" "$out/$lane/postfilter.symvers" "$out/$lane/engine/Module.symvers" > "$out/$lane/dependencies.symvers"
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/provider" QTN_GPL={q(qtn)} QDRV_COMPAT={q(compat)} KBUILD_EXTRA_SYMBOLS="$out/$lane/dependencies.symvers" KCFLAGS="-ffile-prefix-map=$out/$lane=/f332-source" -j2 modules > "$out/provider-$lane.log" 2>&1
 "${{tc}}nm" -u "$out/$lane/provider/qtn_radar_f332.ko" > "$out/provider-imports-$lane.txt"
 "${{tc}}nm" -u "$out/$lane/engine/f332_detector_engine.ko" > "$out/engine-imports-$lane.txt"
done
cmp "$out/a/provider/qtn_radar_f332.ko" "$out/b/provider/qtn_radar_f332.ko"
cmp "$out/a/engine/f332_detector_engine.ko" "$out/b/engine/f332_detector_engine.ko"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=240)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 errors=[];artifacts={}
 if p.returncode:errors.append('kernel bundle build/tests failed')
 vmlinux=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.vmlinux'
 require(sha(vmlinux)=='8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc','F321 export proof drift')
 with vmlinux.open('rb') as f:
  kernel_symbols=ELFFile(f).get_section_by_name('.symtab');kernel_exports={s.name[len('__ksymtab_'):] for s in kernel_symbols.iter_symbols() if s.name.startswith('__ksymtab_')}
 dependency_exports=set()
 for path in (out/'platform.symvers',out/'a/preprocess.symvers',out/'a/postfilter.symvers',out/'a/engine/Module.symvers'):
  if path.exists():dependency_exports.update(line.split()[1] for line in path.read_text().splitlines() if line.strip())
 for name in ('provider','engine'):
  path=out/(name+'-imports-a.txt')
  if path.exists():
   imports={line.split()[-1] for line in path.read_text().splitlines() if line.strip()}
   if imports-kernel_exports-dependency_exports:errors.append(name+' imports absent from exact F321/dependency exports: '+str(sorted(imports-kernel_exports-dependency_exports)))
 for name,rel,license in (('provider','provider/qtn_radar_f332.ko','GPL'),('engine','engine/f332_detector_engine.ko','Proprietary')):
  path=out/'a'/rel
  if not path.exists():continue
  artifacts[name]={'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
  with path.open('rb') as f:
   elf=ELFFile(f);info=elf.get_section_by_name('.modinfo').data()
   if ('license='+license+'\0').encode() not in info or b'vermagic=5.10.260-openmitrastar-radiohw' not in info:errors.append(name+' identity mismatch')
   artifacts[name]['modinfo']=info.decode(errors='replace').split('\0')
 status='FAIL' if errors else ('PASS_OFFLINE_KERNEL_BUNDLE' if capture_qualified else 'BUILD_PASS_CAPTURE_ORACLE_PENDING')
 report={'schema':'openmitrastar.f332-kernel-bundle/v1','status':status,'errors':errors,'sources':sources,'artifacts':artifacts,'capture_oracle_qualified':capture_qualified,'capture_oracle':str(args.f333_result) if args.f333_result else None,'pipeline_oracle':str(PIPE/'result.json'),'pipeline_oracle_sha256':sha(PIPE/'result.json'),'event_tests':(out/'event-tests.txt').read_text() if (out/'event-tests.txt').exists() else None,'hardware_actions':False,'module_loaded':False,'firmware_created':False,'release_qualified':False,'default_hardware_enable':False,'callback_default':False,'reproducible':not errors}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':status,'errors':errors,'artifacts':artifacts},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
