"""Link/run the complete F332 arithmetic pipeline with both exact OEM objects."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f332_dfs_provider'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
CAP=BASE/'f332-capacity-20260921T104538Z'
PRE=BASE/'f330-preprocess-20260921T103429Z'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 cap=json.loads((CAP/'result.json').read_text());pre=json.loads((PRE/'result.json').read_text())
 require(cap['status']=='PASS_OEM_CAPACITY256_TIMESTAMP32','capacity oracle missing')
 require(pre['status']=='PASS_ORIGINAL_PREPROCESS_QEMU_NO_HARDWARE','preprocess oracle missing')
 for n in ('f328-oem-classifier.o','eu-profile.h'):require(sha(CAP/n)==cap['artifacts'][n]['sha256'],'classifier input drift')
 require(sha(PRE/'f330-oem-preprocess.o')==pre['projection']['object_sha256'],'preprocess object drift')
 out=BASE/('f332-pipeline-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 sources={}
 for sub in ('engine','provider','tests'):
  (out/sub).mkdir()
  for p in (SOURCE/sub).iterdir():
   if p.is_file():(out/sub/p.name).write_bytes(p.read_bytes());sources[str(p.relative_to(ROOT))]=sha(p)
 (out/'components').mkdir()
 for unit,names in (('f330_oem_preprocess',('f330_preprocess.c','f330_preprocess.h')),('f331_postfilter',('f331_postfilter.c','f331_postfilter.h'))):
  for n in names:
   p=ROOT/'work/kernel-port/modules'/unit/n;(out/'components'/n).write_bytes(p.read_bytes());sources[str(p.relative_to(ROOT))]=sha(p)
 for n in ('f328-oem-classifier.o','eu-profile.h'):(out/n).write_bytes((CAP/n).read_bytes())
 (out/'f330-oem-preprocess.o').write_bytes((PRE/'f330-oem-preprocess.o').read_bytes())
 (out/'qemu.ld').write_bytes((CAP/'qemu.ld').read_bytes())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
for unit in engine/f328_legacy_abi engine/f332_detector_core provider/f332_pipeline components/f330_preprocess components/f331_postfilter tests/f332_pipeline_qemu; do
 name=$(basename "$unit")
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -DF330_TEST -I"$out" -I"$out/engine" -I"$out/provider" -I"$out/components" -c "$out/$unit.c" -o "$out/$name.o"
done
"${{tc}}gcc" -c "$out/tests/f332_pipeline_entry.S" -o "$out/entry.o"
"${{tc}}gcc" -nostdlib -Wl,-T,"$out/qemu.ld" -o "$out/qemu.elf" "$out/entry.o" "$out/f332_pipeline_qemu.o" "$out/f332_pipeline.o" "$out/f332_detector_core.o" "$out/f328_legacy_abi.o" "$out/f328-oem-classifier.o" "$out/f330_preprocess.o" "$out/f330-oem-preprocess.o" "$out/f331_postfilter.o" -lgcc
"${{tc}}nm" -u "$out/qemu.elf" > "$out/undefined.txt"
test ! -s "$out/undefined.txt"
set +e
timeout 15s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
f332_rc=$?
printf '%s\\n' "$f332_rc" > "$out/qemu-exit.txt"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
 (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
 errors=[];serial=(out/'serial.log').read_text() if (out/'serial.log').exists() else ''
 if p.returncode:errors.append('build failed')
 m=re.fullmatch(r'F332_PIPELINE_BEGIN oem_classifier=1 oem_preprocess=1 actual_hardware=0\nF332_PIPELINE_DONE checks=([0-9a-f]{8}) failures=00000000 hardware=0 callback_authority=0\n',serial)
 if not m or int(m.group(1),16)<100:errors.append('pipeline assertions incomplete/failed')
 for n in ('qemu.stderr','guest-errors.log'):
  if not (out/n).exists() or (out/n).stat().st_size:errors.append(n+' nonempty/missing')
 if not (out/'qemu-exit.txt').exists() or (out/'qemu-exit.txt').read_text().strip()!='0':errors.append('QEMU did not exit zero')
 report={'schema':'openmitrastar.f332-pipeline-oracle/v1','status':'PASS_OEM_PIPELINE_QEMU' if not errors else 'FAIL','errors':errors,'checks':int(m.group(1),16) if m else None,'sources':sources,'hardware_actions':False,'actual_backend':False,'firmware':False,'callback_authority':False,'artifacts':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':report['status'],'errors':errors,'serial':serial,'stderr':p.stderr.decode(errors='replace')[-2500:]},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
