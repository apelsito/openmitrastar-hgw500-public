"""Project exact OEM classifier bytes into a private ARC relocatable object.

No code execution, module load, firmware build, network or device operations.
GNU ARC ld subsequently validates this real ET_REL against an explicit facade.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from datetime import datetime, timezone
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
import f315_oem_radar_oracle as donor

ROOT = Path(__file__).resolve().parents[1]
OEM = ROOT/'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/radar/radar.ko'
EXPECTED = '3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332'
START, END = 0x8e8c, 0xce94
IMPORTS = {'__udivsi3','__umodsi3','memcpy','memset','printk','jiffies',
           'do_gettimeofday','init_timer_key','mod_timer','del_timer'}

def sha(data): return hashlib.sha256(data).hexdigest()
def require(condition, detail):
    if not condition: raise ValueError(detail)

def emit(out):
    original = OEM.read_bytes()
    require(len(original)==109112 and sha(original)==EXPECTED,'OEM binary provenance mismatch')
    with OEM.open('rb') as stream:
        elf = ELFFile(stream)
        old_sections = list(elf.iter_sections())
        symtab = elf.get_section_by_name('.symtab')
        # Only classifier code; the old module, proc handlers, worker, MMIO,
        # fixups and Linux 2.6 delayed-work initializer are never included.
        specs = [('',0,0,b'',0),
                 ('.text.f328_oem',1,6,elf.get_section_by_name('.text').data()[START:END],4),
                 ('.rodata.f328_oem',1,2,elf.get_section_by_name('.rodata').data(),4),
                 ('.data.f328_oem',1,3,elf.get_section_by_name('.data').data()[0x30:],4),
                 ('.bss.f328_oem',8,3,b'',4),
                 ('.rodata.str1.4.f328_oem',1,2,elf.get_section_by_name('.rodata.str1.4').data(),4)]
        section_map = {1:(1,START),3:(2,0),4:(3,0x30),6:(4,0),31:(5,0)}
        # Local section symbols first, then global namespaced functions/data/imports.
        symbols=[('',0,0,0,0,0)]
        section_symbols={}
        for i in range(1,6):
            section_symbols[i]=len(symbols); symbols.append(('',0,0,3,0,i))
        named={}
        def named_symbol(name,value=0,size=0,typ=0,section=0):
            if name not in named:
                named[name]=len(symbols); symbols.append((name,value,size,0x10|typ,0,section))
            return named[name]
        # Expose bounded buffers and exact functions for a new host facade only.
        named_symbol('f328_oem_bss',0,0x9458,1,4)
        named_symbol('f328_oem_text',0,END-START,2,1)
        for s in symtab.iter_symbols():
            if s['st_shndx']==1 and START<=int(s['st_value'])<END and s['st_info']['type']=='STT_FUNC':
                named_symbol('f328_oem_'+s.name,int(s['st_value'])-START,int(s['st_size']),2,1)
        rows=[]; required=set(); relabytes=bytearray()
        for section in old_sections:
            if not isinstance(section,RelocationSection) or old_sections[section['sh_info']].name!='.text': continue
            for rel in section.iter_relocations():
                off=int(rel['r_offset'])
                if not START<=off<END: continue
                typ=int(rel['r_info_type']); require(typ in (4,27),'unexpected ARC relocation')
                s=symtab.get_symbol(rel['r_info_sym']); target=s['st_shndx']
                value=int(s['st_value'])+int(rel['r_addend'])
                if target=='SHN_UNDEF':
                    require(s.name in IMPORTS,'unexpected external import '+s.name)
                    new_name='f328_abi_'+s.name; required.add(s.name)
                    idx=named_symbol(new_name); addend=int(rel['r_addend'])
                elif target==1 and value==0xa4:
                    new_name='f328_abi_radar_ocac_info_addr_get'
                    idx=named_symbol(new_name); addend=0
                else:
                    require(target in section_map,('unexpected section',s.name,target))
                    newsec,base=section_map[target]
                    if target==1: require(START<=value<END,('text escape',hex(off),hex(value)))
                    if target==4: require(value>=0x30,('legacy work-data reference',hex(off),hex(value)))
                    idx=section_symbols[newsec]; addend=value-base; new_name=specs[newsec][0]
                relabytes.extend(struct.pack('<IIi',off-START,(idx<<8)|typ,addend))
                rows.append({'original_offset':off,'type':typ,'original_symbol':s.name,
                             'original_section':target,'original_addend':int(rel['r_addend']),
                             'projected_symbol':new_name,'projected_addend':addend})
        require(required==IMPORTS and len(rows)==1008,'classifier dependency closure drift')
        strtab=bytearray(b'\0'); symbytes=bytearray()
        for name,value,size,info,other,section in symbols:
            nameoff=len(strtab) if name else 0
            if name: strtab.extend(name.encode()+b'\0')
            symbytes.extend(struct.pack('<IIIBBH',nameoff,value,size,info,other,section))
        specs += [('.rela.text.f328_oem',4,0,bytes(relabytes),4),
                  ('.symtab',2,0,bytes(symbytes),4),('.strtab',3,0,bytes(strtab),1)]
        shstr=bytearray(b'\0'); nameoffs=[]
        for name,*_ in specs+[('.shstrtab',)]:
            nameoffs.append(len(shstr) if name else 0)
            if name: shstr.extend(name.encode()+b'\0')
        specs.append(('.shstrtab',3,0,bytes(shstr),1))
        payload=bytearray(b'\0'*52); headers=[]
        for i,(name,typ,flags,data,align) in enumerate(specs):
            while align and len(payload)%align: payload.append(0)
            offset=len(payload); payload.extend(data)
            size=0x9458 if typ==8 else len(data)
            link,info,entsize=(7,1,12) if typ==4 else ((8,6,16) if typ==2 else (0,0,0))
            headers.append(struct.pack('<IIIIIIIIII',nameoffs[i],typ,flags,0,offset,size,link,info,align,entsize))
        while len(payload)%4: payload.append(0)
        shoff=len(payload); payload.extend(b''.join(headers))
        ident=b'\x7fELF\x01\x01\x01'+b'\0'*9
        payload[:52]=struct.pack('<16sHHIIIIIHHHHHH',ident,1,93,1,0,0,shoff,int(elf['e_flags']),52,0,0,40,len(specs),9)
        target=out/'f328-oem-classifier.o'; target.write_bytes(payload)
        # Read our emitted object independently and compare every preserved byte.
        with target.open('rb') as result:
            projected=ELFFile(result)
            require(projected.get_section_by_name('.text.f328_oem').data()==elf.get_section_by_name('.text').data()[START:END],'classifier bytes changed')
            require(projected.get_section_by_name('.data.f328_oem').data()==elf.get_section_by_name('.data').data()[0x30:],'classifier constants changed')
            require(projected.get_section_by_name('.rela.text.f328_oem').num_relocations()==1008,'relocation count changed')
        instructions=donor.parse_disassembly(ROOT/'outputs/kernel-port/f303-oem-radar-re-20260904/objdump-dr.txt')
        escaped=[i for i in instructions if START<=i['address']<END and i['direct_target'] is not None and not START<=i['direct_target']<END]
        require(not escaped,'direct branch escapes classifier closure')
        result={'schema':'openmitrastar.f328-oem-classifier-projection/v1',
                'created_at':datetime.now(timezone.utc).isoformat(),
                'oem_sha256':EXPECTED,'projection_sha256':sha(payload),'text_start':START,'text_end':END,
                'text_bytes':END-START,'text_sha256':sha(specs[1][3]),'relocations':rows,
                'imports':sorted(required),'additional_facade':['radar_ocac_info_addr_get'],
                'direct_branch_escapes':escaped,'entrypoint_zero_valid_for_et_rel':True,
                'old_module_init_present':False,'old_delayed_work_present':False,
                'old_proc_handlers_present':False,'old_mmio_worker_present':False,
                'execution_performed':False,'profile_status':'NOT_YET_BOUND_TO_EFFECTIVE_OEM_EU_INITIALIZATION',
                'not_a_firmware':True,'not_a_loadable_module':True}
        (out/'projection.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':'PROJECTED_EXACT_BYTES_RELOCATIONS_UNAPPLIED','output':str(out),
                          'text_bytes':END-START,'relocations':len(rows),'imports':len(required)}))

if __name__=='__main__':
    output=Path(sys.argv[1]).resolve(); output.mkdir(parents=True,exist_ok=False); emit(output)
