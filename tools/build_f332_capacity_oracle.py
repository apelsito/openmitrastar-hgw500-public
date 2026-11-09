"""Qualify OEM classifier capacity/timestamp domain in QEMU; no device IO."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
from f331_oem_postfilter_projection import linux,require
import f328_oem_classifier_projection as projection
from f328_eu_profile import derive
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/modules/f332_dfs_provider'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=BASE/('f332-capacity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 for rel in ('engine/f328_legacy_abi.c','engine/f328_legacy_abi.h','tests/f332_capacity.c','tests/f332_capacity_entry.S'):(out/Path(rel).name).write_bytes((SRC/rel).read_bytes())
 projection.emit(out);derive(out)
 (out/'qemu.ld').write_text('ENTRY(_start)\nSECTIONS{. = 0x80000000; .text : {*(.text.entry) *(.text*)} .rodata : {*(.rodata*)} .data : {*(.data*)} .bss : {*(.bss*) *(COMMON)} /DISCARD/ : {*(.comment) *(.note*) *(.eh_frame*)}}\n')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
for unit in f328_legacy_abi f332_capacity; do
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -I"$out" -c "$out/$unit.c" -o "$out/$unit.o"
done
"${{tc}}gcc" -c "$out/f332_capacity_entry.S" -o "$out/entry.o"
"${{tc}}ld" -T "$out/qemu.ld" -o "$out/qemu.elf" "$out/entry.o" "$out/f332_capacity.o" "$out/f328_legacy_abi.o" "$out/f328-oem-classifier.o"
set +e
timeout 12s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
f332_rc=$?
printf '%s\\n' "$f332_rc" > "$out/qemu-exit.txt"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
 (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
 errors=[];rows=[];serial=(out/'serial.log').read_text() if (out/'serial.log').exists() else ''
 lines=serial.splitlines()
 if p.returncode:errors.append('build failed')
 if len(lines)!=112 or lines[0]!='F332_CAPACITY_BEGIN OEM_BYTES_UNCHANGED=1' or lines[-1]!='F332_CAPACITY_DONE vectors=110 hardware=0':errors.append('incomplete output')
 pattern=r'F332_CAP count=([0-9a-f]{8}) base=([0-9a-f]{8}) current=([0-9a-f]{8}) poison=([0-9a-f]{8}) detected=([0-9a-f]{8}) poll=([0-9a-f]{8}) ssr=([0-9a-f]{8})'
 for line in lines[1:-1]:
  m=re.fullmatch(pattern,line)
  if not m:errors.append('invalid row');continue
  count,base,current,poison,detected,poll,ssr=[int(x,16) for x in m.groups()]
  rows.append({'count':count,'base':base,'current':current,'poison':poison,'detected':detected,'poll':poll,'ssr':ssr})
  if (detected,poll,ssr)!=(int(count>=8),0,int(count>=8)):errors.append('unexpected semantics '+line)
 for n in ('qemu.stderr','guest-errors.log'):
  if not (out/n).exists() or (out/n).stat().st_size:errors.append(n+' nonempty/missing')
 if not (out/'qemu-exit.txt').exists() or (out/'qemu-exit.txt').read_text().strip()!='0':errors.append('QEMU exit not zero')
 result={'schema':'openmitrastar.f332-capacity-oracle/v1','status':'PASS_OEM_CAPACITY256_TIMESTAMP32' if not errors else 'FAIL','errors':errors,'rows':rows,'hardware_actions':False,'linux_facade_capacity_change_authorized_by_oracle':not errors,'artifacts':{x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in out.iterdir() if x.is_file()}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'path':str(out/'result.json'),'status':result['status'],'errors':errors,'tail':serial[-1500:],'stderr':p.stderr.decode()[-1500:]},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
