"""Build reproducible ARC Linux userspace service; do not open its device."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f338'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
CAP=BASE/'f332-capacity-20260921T104538Z'
PRE=BASE/'f330-preprocess-20260921T103429Z'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=BASE/('f338-service-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 for sub in ('userspace','uapi'):
  (out/sub).mkdir()
  for p in (SOURCE/sub).iterdir():
   if p.is_file():(out/sub/p.name).write_bytes(p.read_bytes())
 cap=json.loads((CAP/'result.json').read_text());pre=json.loads((PRE/'result.json').read_text())
 require(cap['status']=='PASS_OEM_CAPACITY256_TIMESTAMP32' and pre['status']=='PASS_ORIGINAL_PREPROCESS_QEMU_NO_HARDWARE','unqualified math inputs')
 for p in (CAP/'f328-oem-classifier.o',CAP/'eu-profile.h',PRE/'f330-oem-preprocess.o'):(out/p.name).write_bytes(p.read_bytes())
 require(sha(out/'f328-oem-classifier.o')==cap['artifacts']['f328-oem-classifier.o']['sha256'],'classifier drift')
 require(sha(out/'f330-oem-preprocess.o')==pre['projection']['object_sha256'],'preprocessor drift')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
src="$out/userspace"
tc={q(tc)}
sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot
for lane in a b; do
 mkdir "$out/$lane"
 for unit in f328_legacy_abi f330_preprocess f332_detector_core f338_selftest f338_service_core f338_service; do
  extra=
  test "$unit" != f338_selftest || extra=-Dmain=f338_selftest_main
  SOURCE_DATE_EPOCH=1790006400 "${{tc}}gcc" --sysroot="$sysroot" -std=c11 -Os -g0 -mno-atomic -mno-sdata -mlong-calls -fno-stack-protector -fno-builtin -Wall -Wextra -Werror -pedantic $extra -DF330_TEST -Df328_oem_detect_init=f338_oem_detect_init -Df328_oem_detect_reset=f338_oem_detect_reset -Df328_oem_detect_radar=f338_oem_detect_radar -Df328_oem_detect_radar_poll=f338_oem_detect_radar_poll -Df330_oem_preprocess=f338_oem_preprocess -I"$out" -I"$src" -I"$out/uapi" -c "$src/$unit.c" -o "$out/$lane/$unit.o"
 done
 "${{tc}}gcc" -mno-atomic -c "$src/f338_oem_thunks.S" -o "$out/$lane/thunks.o"
 "${{tc}}gcc" --sysroot="$sysroot" -mno-atomic -static -Wl,--build-id=none -o "$out/$lane/om-radar-engine-f338" "$out/$lane/"*.o "$out/f328-oem-classifier.o" "$out/f330-oem-preprocess.o"
 "${{tc}}objdump" -d "$out/$lane/om-radar-engine-f338" > "$out/$lane/disassembly.txt"
 ! grep -Eq '\\b(llock|scond|flag)\\b' "$out/$lane/disassembly.txt"
 ! grep -E '\\b(lr|sr)\\b' "$out/$lane/disassembly.txt" | grep -v 'lp_start' > "$out/$lane/unexpected-aux.txt"
 "${{tc}}strip" --strip-unneeded "$out/$lane/om-radar-engine-f338"
done
cmp "$out/a/om-radar-engine-f338" "$out/b/om-radar-engine-f338"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=150)
 (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
 binary=out/'a/om-radar-engine-f338';errors=[]
 if p.returncode:errors.append('build/instruction audit failed')
 if binary.exists():
  with binary.open('rb') as f:
   elf=ELFFile(f);require(elf['e_machine'] in ('EM_ARC','EM_ARC_COMPACT'),'wrong CPU');require(not any(s['p_type']=='PT_INTERP' for s in elf.iter_segments()),'not static')
 result={'schema':'openmitrastar.f338-service/v1','status':'PASS_STATIC_SERVICE_BUILD' if not errors else 'FAIL','errors':errors,'binary':{'path':str(binary),'bytes':binary.stat().st_size,'sha256':sha(binary)} if binary.exists() else None,'hardware':False,'uapi_opened':False,'reproducible':not errors,'sources':{str(p.relative_to(out)):sha(p) for sub in ('userspace','uapi') for p in (out/sub).iterdir() if p.is_file()},'execution':'UNRUN','GPL_kernel_code_linked':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result,'build_error_tail':p.stderr.decode(errors='replace')[-2500:]},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
