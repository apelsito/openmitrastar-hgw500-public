"""Project exact pure OEM postfilter blocks for a PRIVATE QEMU oracle only.

Preserves [43c0,4c06) and [4c80,4cb0). At 4c06 a new return trampoline replaces
the scheduler/PM tail. No original module/init/MMIO/lifecycle is included.
"""
from pathlib import Path
import hashlib,json
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
import f315_oem_radar_oracle as donor
ROOT=Path(__file__).resolve().parents[1]
OEM=ROOT/'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/radar/radar.ko'
EXPECTED='3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332'
START,EXIT,ISLAND,END=0x43c0,0x4c06,0x4c80,0x4cb0
def sha(b):return hashlib.sha256(b).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def linux(p):return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def included(n):return START<=n<EXIT or ISLAND<=n<END
def emit(out):
 raw=OEM.read_bytes();require(sha(raw)==EXPECTED,'OEM provenance mismatch')
 with OEM.open('rb') as stream:
  elf=ELFFile(stream);sections=list(elf.iter_sections());sym=elf.get_section_by_name('.symtab');text=elf.get_section_by_name('.text').data()
  for name,data in [('prefix.bin',text[START:EXIT]),('island.bin',text[ISLAND:END]),('strings.bin',elf.get_section_by_name('.rodata.str1.4').data()),('rodata.bin',elf.get_section_by_name('.rodata').data())]:(out/name).write_bytes(data)
  code=['.section .text.f331_oem,"ax",@progbits','.balign 4','.global f331_oem_slice','f331_oem_slice:',f'.incbin "{linux(out/"prefix.bin")}"','mov r12,f331_asm_return','j [r12]',f'.org {ISLAND-START}',f'.incbin "{linux(out/"island.bin")}"']
  rows=[]
  for sec in sections:
   if not isinstance(sec,RelocationSection) or sections[sec['sh_info']].name!='.text':continue
   for rel in sec.iter_relocations():
    off=int(rel['r_offset'])
    if not included(off):continue
    require(int(rel['r_info_type'])==27,'non-32-ME relocation in postfilter')
    s=sym.get_symbol(rel['r_info_sym']);target=s['st_shndx'];value=int(s['st_value'])+int(rel['r_addend'])
    if target==6:name='f331_oem_bss';require(0<=value<0x9458,'BSS bounds')
    elif target==3:name='f331_rodata'
    elif target==31:name='f331_strings'
    elif target=='SHN_UNDEF' and s.name=='printk':name='f331_oracle_printk';require(value==0,'printk addend')
    else:raise ValueError(('unexpected dependency',hex(off),s.name,target,value))
    code.append(f'.reloc f331_oem_slice+{off-START},R_ARC_32_ME,{name}+{value}')
    rows.append({'offset':off,'symbol':name,'addend':value})
  code+=['.section .rodata.f331,"a",@progbits','.balign 4','f331_rodata:',f'.incbin "{linux(out/"rodata.bin")}"','f331_strings:',f'.incbin "{linux(out/"strings.bin")}"','.section .bss.f331,"aw",@nobits','.balign 4','.global f331_oem_bss','f331_oem_bss:','.space 37976']
  (out/'oem-projection.S').write_text('\n'.join(code)+'\n',newline='\n')
  instructions=donor.parse_disassembly(ROOT/'outputs/kernel-port/f303-oem-radar-re-20260904/objdump-dr.txt')
  escaped=[i for i in instructions if included(i['address']) and i['direct_target'] is not None and not(included(i['direct_target']) or i['direct_target']==EXIT)]
  require(not escaped,'direct branch escapes pure postfilter')
  report={'oem_sha256':EXPECTED,'intervals':[[START,EXIT],[ISLAND,END]],'preserved_bytes':EXIT-START+END-ISLAND,'preserved_sha256':sha(text[START:EXIT]+text[ISLAND:END]),'relocations':rows,'return_trampoline_offset':EXIT,'excluded_tail':[EXIT,ISLAND],'hardware_actions':False,'callback':'private counter stub in QEMU only','scheduler_pm_tail_present':False,'old_module_present':False}
  (out/'projection.json').write_text(json.dumps(report,indent=2)+'\n')
  return report
