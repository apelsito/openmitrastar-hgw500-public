"""Run source-versus-exact-OEM postfilter differential tests in local ARC QEMU."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,subprocess
from elftools.elf.elffile import ELFFile
import f331_oem_postfilter_projection as projection
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/modules/f331_postfilter'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 out=BASE/('f331-postfilter-'+stamp);out.mkdir(parents=True,exist_ok=False)
 snapshot=out/'source';snapshot.mkdir()
 for p in SRC.iterdir():
  if p.is_file():(snapshot/p.name).write_bytes(p.read_bytes())
 proof=projection.emit(out)
 (out/'qemu.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.entry) *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n')
 q=shlex.quote;linux=projection.linux
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
src={q(linux(snapshot))}
tc={q(tc)}
"${{tc}}gcc" -c "$out/oem-projection.S" -o "$out/oem-projection.o"
"${{tc}}gcc" -c "$src/f331_oracle_entry.S" -o "$out/entry.o"
for unit in f331_postfilter f331_oracle_harness; do
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -I"$src" -c "$src/$unit.c" -o "$out/$unit.o"
done
"${{tc}}gcc" -nostdlib -Wl,-T,"$out/qemu.ld" -o "$out/qemu.elf" "$out/entry.o" "$out/oem-projection.o" "$out/f331_postfilter.o" "$out/f331_oracle_harness.o" -lgcc
"${{tc}}nm" -u "$out/qemu.elf" > "$out/undefined.txt"
test ! -s "$out/undefined.txt"
"${{tc}}objdump" -dr "$out/qemu.elf" > "$out/linked-disassembly.txt"
sha256sum /home/user/qemu-arc-legacy-build/qemu-system-arc > "$out/qemu-sha256.txt"
set +e
timeout 15s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
f331_rc=$?
printf '%s\\n' "$f331_rc" > "$out/qemu-exit.txt"
exit 0
'''
 (out/'build.sh').write_bytes(script.encode())
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
 (out/'build.stdout').write_bytes(run.stdout);(out/'build.stderr').write_bytes(run.stderr)
 errors=[]
 if run.returncode:errors.append('build failed')
 if (out/'oem-projection.o').exists():
  with (out/'oem-projection.o').open('rb') as f:
   elf=ELFFile(f);data=elf.get_section_by_name('.text.f331_oem').data()
   if data[:projection.EXIT-projection.START]!=(out/'prefix.bin').read_bytes() or data[projection.ISLAND-projection.START:projection.END-projection.START]!=(out/'island.bin').read_bytes():errors.append('preserved OEM bytes drift')
 serial=(out/'serial.log').read_text(errors='replace') if (out/'serial.log').exists() else ''
 expected=['F331_ORACLE_BEGIN preserved_oem_blocks=1 hardware=0','F331_ORACLE_DONE compared=000014f0 fault=00000000 callback_authority=0']
 if serial.splitlines()!=expected:errors.append('differential corpus incomplete or mismatch')
 for name in ('qemu.stderr','guest-errors.log'):
  if not (out/name).exists() or (out/name).stat().st_size:errors.append(name+' nonempty/missing')
 if not (out/'qemu-exit.txt').exists() or (out/'qemu-exit.txt').read_text().strip()!='0':errors.append('QEMU did not exit zero')
 result={'schema':'openmitrastar.f331-postfilter-oracle/v1','status':'PASS_EXACT_OEM_DIFFERENTIAL' if not errors else 'FAIL','errors':errors,'compared_vectors':5360 if not errors else None,'preserved_oem_bytes':proof['preserved_bytes'],'oem_sha256':projection.EXPECTED,'hardware_actions':False,'firmware_created':False,'callback_authority':False,'source_hashes':{p.name:sha(p) for p in snapshot.iterdir() if p.is_file()},'artifacts':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'result':str(out/'result.json'),'status':result['status'],'errors':errors,'serial':serial,'stderr':run.stderr.decode(errors='replace')[-2500:]},indent=2))
 return bool(errors)
if __name__=='__main__':raise SystemExit(main())
