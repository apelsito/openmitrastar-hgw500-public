"""Recover/compare OEM OCAC worker metadata against a portable C model in QEMU."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from f331_oem_postfilter_projection import OEM,EXPECTED,ROOT,linux,require
import f315_oem_radar_oracle as donor
SOURCE=ROOT/'work/kernel-port/modules/f332_dfs_provider'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
START,END=0x3c32,0x3dde
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 require(sha(OEM)==EXPECTED,'OEM provenance mismatch')
 out=BASE/('f332-ocac-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 files=('provider/f332_ocac.c','provider/f332_ocac.h','provider/f316_portable.h','tests/f332_ocac_entry.S','tests/f332_ocac_qemu.c')
 for rel in files:(out/Path(rel).name).write_bytes((SOURCE/rel).read_bytes())
 with OEM.open('rb') as f:
  elf=ELFFile(f);sections=list(elf.iter_sections());symbols=elf.get_section_by_name('.symtab');original=elf.get_section_by_name('.text').data()[START:END];data=bytearray(original)
  # Single known physical load becomes a fake RAM cell in this oracle only.
  data[0x3d4c-START:0x3d50-START]=b'\0'*4;(out/'body.bin').write_bytes(data)
  (out/'strings.bin').write_bytes(elf.get_section_by_name('.rodata.str1.4').data());(out/'rodata.bin').write_bytes(elf.get_section_by_name('.rodata').data())
  code=['.section .text.f332_ocac,"ax",@progbits','.balign 4','.short 0','.global f332_ocac_original','f332_ocac_original:',f'.incbin "{linux(out/"body.bin")}"','mov r12,f332_ocac_return','j [r12]']
  rows=[]
  for sec in sections:
   if not isinstance(sec,RelocationSection) or sections[sec['sh_info']].name!='.text':continue
   for rel in sec.iter_relocations():
    off=int(rel['r_offset'])
    if not START<=off<END:continue
    require(int(rel['r_info_type'])==27,'unexpected relocation type')
    symbol=symbols.get_symbol(rel['r_info_sym']);target=symbol['st_shndx'];value=int(symbol['st_value'])+int(rel['r_addend'])
    if symbol.name in ('qtn_bb_mutex_enter_dbg','qtn_bb_mutex_leave_dbg'):
     require(int(rel['r_addend'])==0,'unexpected BB helper addend');name='f332_ocac_enter' if symbol.name=='qtn_bb_mutex_enter_dbg' else 'f332_ocac_leave';value=0
    elif target==6:name='f332_ocac_bss'
    elif target==3:name='f332_ocac_rodata'
    elif target==31:name='f332_ocac_strings'
    elif target==1:
     require(START<=value<END,'branch escape');name='f332_ocac_original';value-=START
    elif target=='SHN_UNDEF':
     mapping={'printk':'f332_ocac_printk','qtn_bb_mutex_enter_dbg':'f332_ocac_enter','qtn_bb_mutex_leave_dbg':'f332_ocac_leave','g_dbg_log_module':'f332_ocac_debug_zero','g_dbg_log_level':'f332_ocac_debug_zero','g_dbg_log_func':'f332_ocac_debug_zero'}
     require(symbol.name in mapping,'unknown import '+symbol.name);name=mapping[symbol.name]
    else:raise ValueError((off,symbol.name,target))
    code.append(f'.reloc f332_ocac_original+{off-START},R_ARC_32_ME,{name}+{value}');rows.append([off,name,value])
  code += [f'.reloc f332_ocac_original+{0x3d4c-START},R_ARC_32_ME,f332_ocac_current','.section .rodata.f332_ocac,"a",@progbits','.balign 4','f332_ocac_rodata:',f'.incbin "{linux(out/"rodata.bin")}"','f332_ocac_strings:',f'.incbin "{linux(out/"strings.bin")}"','.section .bss.f332_ocac,"aw",@nobits','.balign 4','.global f332_ocac_bss','f332_ocac_bss:','.space 37984','f332_ocac_debug_zero:','.space 4']
  (out/'projection.S').write_text('\n'.join(code)+'\n',newline='\n')
  instructions=donor.parse_disassembly(ROOT/'outputs/kernel-port/f303-oem-radar-re-20260904/objdump-dr.txt')
  escapes=[i for i in instructions if START<=i['address']<END and i['direct_target'] is not None and not START<=i['direct_target']<=END];require(not escapes,'direct branch escaped')
  (out/'projection.json').write_text(json.dumps({'OEM':EXPECTED,'start':START,'end':END,'original_sha256':hashlib.sha256(original).hexdigest(),'mapped_physical_load':0x3d48,'relocations':rows,'pc_mod4':2,'hardware':False},indent=2)+'\n')
 (out/'qemu.ld').write_text('ENTRY(_start)\nSECTIONS{. = 0x80000000; .text : {*(.text.entry) *(.text*)} .rodata : {*(.rodata*)} .data : {*(.data*)} .bss : {*(.bss*) *(COMMON)} /DISCARD/ : {*(.comment) *(.note*) *(.eh_frame*)}}\n')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
for unit in f332_ocac f332_ocac_qemu; do
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -I"$out" -c "$out/$unit.c" -o "$out/$unit.o"
done
"${{tc}}gcc" -c "$out/f332_ocac_entry.S" -o "$out/entry.o"
"${{tc}}gcc" -c "$out/projection.S" -o "$out/original.o"
"${{tc}}gcc" -nostdlib -Wl,-T,"$out/qemu.ld" -o "$out/qemu.elf" "$out/entry.o" "$out/original.o" "$out/f332_ocac.o" "$out/f332_ocac_qemu.o" -lgcc
set +e
timeout 15s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
f332_rc=$?
printf '%s\\n' "$f332_rc" > "$out/qemu-exit.txt"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=80)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr);errors=[]
 if p.returncode:errors.append('build failed')
 serial=(out/'serial.log').read_text() if (out/'serial.log').exists() else ''
 m=re.fullmatch(r'F332_OCAC_BEGIN hardware=0\nF332_OCAC_DONE vectors=00000800 checks=([0-9a-f]{8}) failures=00000000\n',serial)
 if not m:errors.append('oracle mismatch/incomplete')
 for name in ('guest-errors.log','qemu.stderr'):
  if not (out/name).exists() or (out/name).stat().st_size:errors.append(name+' nonempty/missing')
 if not (out/'qemu-exit.txt').exists() or (out/'qemu-exit.txt').read_text().strip()!='0':errors.append('QEMU did not exit0')
 result={'schema':'openmitrastar.f332-ocac-oracle/v1','status':'PASS_OCAC_METADATA_VS_OEM' if not errors else 'FAIL','errors':errors,'checks':int(m.group(1),16) if m else None,'vectors':2048 if m else None,'sources':{rel:sha(SOURCE/rel) for rel in files},'hardware':False,'callback_authority':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result,'serial':serial,'stderr':p.stderr.decode()[-1600:]},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
