"""Qualify pure F331 C core and two reproducible ARC Linux 5.10 modules offline."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shlex,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f331_postfilter'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--oracle-dir',required=True,type=Path);args=ap.parse_args();oracle=args.oracle_dir.resolve()
 report=json.loads((oracle/'result.json').read_text());require(report['status']=='PASS_EXACT_OEM_DIFFERENTIAL' and report['compared_vectors']==5360,'oracle not qualified')
 for name in ('f331_postfilter.c','f331_postfilter.h'):require(sha(SOURCE/name)==report['source_hashes'][name],'core source changed since oracle')
 for name,meta in report['artifacts'].items():require(sha(oracle/name)==meta['sha256'],'oracle artifact drift '+name)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=BASE/('f331-kernel-'+stamp);out.mkdir(parents=True,exist_ok=False)
 files=('Makefile','f331_module.c','f331_postfilter.c','f331_postfilter.h','test_f331_native.c')
 for lane in ('a','b'):
  (out/lane).mkdir()
  for name in files:(out/lane/name).write_bytes((SOURCE/name).read_bytes())
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src=/home/user/mitrastar-linux-5.10.260
kout=/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic "$out/a/f331_postfilter.c" "$out/a/test_f331_native.c" -o "$out/test-native"
"$out/test-native" > "$out/native-tests.txt"
cc -std=c11 -Wall -Wextra -Werror -pedantic -fanalyzer -fsyntax-only "$out/a/f331_postfilter.c" > "$out/analyzer.txt" 2>&1
for lane in a b; do
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \\
 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane" KCFLAGS="-ffile-prefix-map=$out/$lane=/f331-source" -j2 modules > "$out/build-$lane.log" 2>&1
 "${{tc}}nm" -u "$out/$lane/f331_postfilter_port.ko" > "$out/imports-$lane.txt"
done
cmp "$out/a/f331_postfilter_port.ko" "$out/b/f331_postfilter_port.ko"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
'''
 (out/'build.sh').write_bytes(script.encode())
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr)
 errors=[]
 if run.returncode:errors.append('native/kernel build failed')
 module=out/'a/f331_postfilter_port.ko';imports=[];checks=None
 if not errors:
  match=re.fullmatch(r'F331_NATIVE_PASS checks=(\d+) hardware=0 callback_authority=0\n',(out/'native-tests.txt').read_text())
  if not match:errors.append('native evidence missing')
  else:checks=int(match.group(1))
  imports={line.split()[-1] for line in (out/'imports-a.txt').read_text().splitlines() if line.strip()}
  if not imports.issubset({'memcpy','memset','__udivsi3','__modsi3','__divsi3'}):errors.append('unexpected imports')
  vmlinux=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.vmlinux'
  with vmlinux.open('rb') as f:
   symbols=ELFFile(f).get_section_by_name('.symtab')
   if not all(symbols.get_symbol_by_name('__ksymtab_'+name) for name in imports):errors.append('missing F321 export')
  with module.open('rb') as f:
   elf=ELFFile(f);info=elf.get_section_by_name('.modinfo').data()
   if b'vermagic=5.10.260-openmitrastar-radiohw' not in info or b'license=GPL\0' not in info:errors.append('module identity mismatch')
  if sha(module)!=sha(out/'b/f331_postfilter_port.ko'):errors.append('module not reproducible')
 result={'schema':'openmitrastar.f331-kernel-offline/v1','status':'PASS_OFFLINE_KERNEL_NO_LOAD' if not errors else 'FAIL','errors':errors,'native_assertions':checks,'gcc_analyzer':'PASS' if not errors else 'NOT_ESTABLISHED','oracle_result':str(oracle/'result.json'),'oracle_sha256':sha(oracle/'result.json'),'differential_vectors':5360,'module':{'path':str(module),'bytes':module.stat().st_size,'sha256':sha(module)} if module.exists() else None,'imports':sorted(imports),'reproducible':not errors,'module_loaded':False,'hardware_actions':False,'firmware_created':False,'callback_authority':False,'sources':{n:sha(SOURCE/n) for n in files}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
