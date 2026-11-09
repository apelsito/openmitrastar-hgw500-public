"""Private arithmetic comparison: new syscall composition vs qualified F332."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f338'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
CAP=BASE/'f332-capacity-20260921T104538Z';PRE=BASE/'f330-preprocess-20260921T103429Z'
REF=ROOT/'work/kernel-port/modules/f332_dfs_provider/provider'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=BASE/('f338-pipeline-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 for sub in ('userspace','kernel','uapi','tests'):
  (out/sub).mkdir()
  for p in (SRC/sub).iterdir():
   if p.is_file():(out/sub/p.name).write_bytes(p.read_bytes())
 (out/'reference').mkdir()
 for name in ('f332_pipeline.c','f332_pipeline.h','f316_portable.h'):(out/'reference'/name).write_bytes((REF/name).read_bytes())
 for p in (CAP/'f328-oem-classifier.o',CAP/'eu-profile.h',PRE/'f330-oem-preprocess.o',CAP/'qemu.ld'):(out/p.name).write_bytes(p.read_bytes())
 cap=json.loads((CAP/'result.json').read_text());pre=json.loads((PRE/'result.json').read_text())
 require(sha(out/'f328-oem-classifier.o')==cap['artifacts']['f328-oem-classifier.o']['sha256'],'OEM classifier drift');require(sha(out/'f330-oem-preprocess.o')==pre['projection']['object_sha256'],'OEM preprocess drift')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
flags="-std=c11 -Os -mno-atomic -mno-sdata -mlong-calls -ffreestanding -fno-builtin -fno-common -Wall -Wextra -Werror -pedantic -DF330_TEST"
rename="-Df328_oem_detect_init=f338_oem_detect_init -Df328_oem_detect_reset=f338_oem_detect_reset -Df328_oem_detect_radar=f338_oem_detect_radar -Df328_oem_detect_radar_poll=f338_oem_detect_radar_poll -Df330_oem_preprocess=f338_oem_preprocess"
for unit in f328_legacy_abi f330_preprocess f332_detector_core f338_service_core; do
 "${{tc}}gcc" $flags $rename -I"$out" -I"$out/userspace" -I"$out/uapi" -c "$out/userspace/$unit.c" -o "$out/$unit.o"
done
for unit in f338_pipeline f331_postfilter; do
 "${{tc}}gcc" $flags -Df332_pipeline_begin=f338_kernel_begin -Df332_pipeline_end=f338_kernel_end -I"$out/kernel" -I"$out/uapi" -c "$out/kernel/$unit.c" -o "$out/$unit.o"
done
"${{tc}}gcc" $flags -I"$out/reference" -I"$out/userspace" -I"$out/kernel" -I"$out/uapi" -c "$out/reference/f332_pipeline.c" -o "$out/old-pipeline.o"
"${{tc}}gcc" $flags -I"$out/reference" -I"$out/userspace" -I"$out/kernel" -I"$out/uapi" -c "$out/tests/oracle_reference.c" -o "$out/reference.o"
"${{tc}}gcc" $flags -Df332_pipeline_begin=f338_kernel_begin -Df332_pipeline_end=f338_kernel_end -I"$out/kernel" -I"$out/userspace" -I"$out/uapi" -c "$out/tests/f338_pipeline_qemu.c" -o "$out/harness.o"
"${{tc}}gcc" -mno-atomic -c "$out/userspace/f338_oem_thunks.S" -o "$out/thunks.o"
"${{tc}}gcc" -mno-atomic -c "$out/tests/f338_oracle_entry.S" -o "$out/entry.o"
"${{tc}}gcc" -mno-atomic -nostdlib -Wl,-T,"$out/qemu.ld" -o "$out/qemu.elf" "$out/"*.o -lgcc
set +e
timeout 20s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
printf '%s\\n' "$?" > "$out/qemu-exit.txt"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=75)
 (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
 serial=(out/'serial.log').read_text() if (out/'serial.log').exists() else '';errors=[]
 match=re.fullmatch(r'F338_ORACLE_BEGIN original_math=1 hardware=0\nF338_ORACLE_DONE checks=([0-9a-f]{8}) failures=00000000 vectors=000000b4 hardware=0\n',serial)
 if p.returncode:errors.append('build failed')
 if not match:errors.append('oracle incomplete or divergent')
 if not (out/'qemu-exit.txt').exists() or (out/'qemu-exit.txt').read_text().strip()!='0':errors.append('QEMU did not exit0')
 for name in ('qemu.stderr','guest-errors.log'):
  if not (out/name).exists() or (out/name).stat().st_size:errors.append(name+' nonempty/missing')
 result={'schema':'openmitrastar.f338-pipeline-oracle/v1','status':'PASS_COMPOSITION_VS_F332_ORACLE' if not errors else 'FAIL','errors':errors,'checks':int(match.group(1),16) if match else None,'vectors':180,'hardware':False,'deployable_artifact':False,'sources':{str(p.relative_to(out)):sha(p) for sub in ('userspace','kernel','reference','uapi','tests') for p in (out/sub).iterdir() if p.is_file()}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':result['status'],'errors':errors,'serial':serial,'stderr':p.stderr.decode(errors='replace')[-3000:]},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
