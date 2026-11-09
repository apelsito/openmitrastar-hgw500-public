"""Private projection of exact OEM preprocessing, with recorded fake hardware.

Only the two absolute MMIO address literals are rebound to separate recorder
cells. The original arithmetic, filters, branches, counters and returns stay
byte-identical. Weak BB helpers become explicit request-recording hooks.
"""
from pathlib import Path
import json,struct
from datetime import datetime,timezone
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from f328_oem_classifier_projection import OEM,EXPECTED,ROOT,sha,require
import f315_oem_radar_oracle as donor
START,END=0x26e8,0x2c14

def emit(out):
    require(sha(OEM.read_bytes())==EXPECTED,'OEM provenance mismatch')
    with OEM.open('rb') as stream:
        elf=ELFFile(stream);old=list(elf.iter_sections());symtab=elf.get_section_by_name('.symtab')
        original=elf.get_section_by_name('.text').data()[START:END]
        code=bytearray(original)
        # Operand LIMM of the two original ST r13,[0xe6091518] instructions.
        patches=[(0x2b4e,0),(0x2b68,4)]
        expected_address=struct.pack('<I',0x1518e609)
        for location,_ in patches:
            require(code[location-START:location-START+4]==expected_address,'MMIO instruction drift')
            code[location-START:location-START+4]=b'\0'*4
        specs=[('',0,0,b'',0),('.text.f330_oem',1,6,bytes(code),4),
               ('.rodata.f330_oem',1,2,elf.get_section_by_name('.rodata').data(),4),
               ('.data.f330_oem',1,3,elf.get_section_by_name('.data').data()[0x2c:0x30],4),
               ('.bss.f330_oem',8,3,b'',4),
               ('.rodata.str1.4.f330_oem',1,2,elf.get_section_by_name('.rodata.str1.4').data(),4)]
        maps={1:(1,START),3:(2,0),4:(3,0x2c),6:(4,0),31:(5,0)}
        symbols=[('',0,0,0,0,0)]+[('',0,0,3,0,i) for i in range(1,6)]
        names={}
        def symbol(name,value=0,size=0,kind=0,section=0):
            if name not in names:names[name]=len(symbols);symbols.append((name,value,size,0x10|kind,0,section))
            return names[name]
        symbol('f330_oem_preprocess',0,END-START,2,1)
        symbol('f330_oem_bss',0,0x9458,1,4)
        symbol('f330_oem_history_pointer',0,4,1,3)
        records=[];rela=bytearray()
        for section in old:
            if not isinstance(section,RelocationSection) or old[section['sh_info']].name!='.text':continue
            for r in section.iter_relocations():
                pos=int(r['r_offset'])
                if not START<=pos<END:continue
                require(int(r['r_info_type'])==27,'unexpected relocation')
                s=symtab.get_symbol(r['r_info_sym']);target=s['st_shndx'];v=int(s['st_value'])+int(r['r_addend'])
                if target=='SHN_UNDEF':
                    require(s.name in ('memcpy','printk','do_gettimeofday'),'unexpected import')
                    name='f330_abi_'+s.name;idx=symbol(name);a=int(r['r_addend'])
                elif s.name in ('qtn_bb_mutex_enter_dbg','qtn_bb_mutex_leave_dbg'):
                    name='f330_abi_bb_'+('enter' if 'enter' in s.name else 'leave');idx=symbol(name);a=0
                else:
                    require(target in maps,'unknown data dependency');new,base=maps[target]
                    require(target!=1 or START<=v<END,'outward code dependency')
                    require(target!=4 or v==0x2c,'unexpected old workqueue data')
                    name=specs[new][0];idx=new;a=v-base
                rela.extend(struct.pack('<IIi',pos-START,(idx<<8)|27,a))
                records.append({'offset':pos,'symbol':name,'addend':a,'original':s.name})
        require(len(records)==68,'original relocation closure changed')
        for pos,cell in patches:
            idx=symbol('f330_recorded_counter_writes')
            rela.extend(struct.pack('<IIi',pos-START,(idx<<8)|27,cell))
            records.append({'offset':pos,'symbol':'f330_recorded_counter_writes','addend':cell,'original':'MMIO 0xe6091518'})
        # The only data word is the OEM initial history pointer (.bss+0x1b40).
        data_rela=struct.pack('<IIi',0,(4<<8)|4,0x1b40)
        strings=bytearray(b'\0');syms=bytearray()
        for name,value,size,info,other,section in symbols:
            off=len(strings) if name else 0
            if name:strings.extend(name.encode()+b'\0')
            syms.extend(struct.pack('<IIIBBH',off,value,size,info,other,section))
        specs += [('.rela.text.f330_oem',4,0,bytes(rela),4),('.rela.data.f330_oem',4,0,data_rela,4),
                  ('.symtab',2,0,bytes(syms),4),('.strtab',3,0,bytes(strings),1)]
        shstr=bytearray(b'\0');offsets=[]
        for name,*_ in specs+[('.shstrtab',)]:
            offsets.append(len(shstr) if name else 0)
            if name:shstr.extend(name.encode()+b'\0')
        specs.append(('.shstrtab',3,0,bytes(shstr),1))
        binary=bytearray(b'\0'*52);headers=[]
        for i,(name,typ,flags,data,align) in enumerate(specs):
            while align and len(binary)%align:binary.append(0)
            off=len(binary);binary.extend(data);size=0x9458 if typ==8 else len(data)
            link,info,entry=(8,1 if i==6 else 3,12) if typ==4 else ((9,6,16) if typ==2 else (0,0,0))
            headers.append(struct.pack('<IIIIIIIIII',offsets[i],typ,flags,0,off,size,link,info,align,entry))
        while len(binary)%4:binary.append(0)
        shoff=len(binary);binary.extend(b''.join(headers))
        binary[:52]=struct.pack('<16sHHIIIIIHHHHHH',b'\x7fELF\x01\x01\x01'+b'\0'*9,1,93,1,0,0,shoff,int(elf['e_flags']),52,0,0,40,len(specs),10)
        (out/'f330-oem-preprocess.o').write_bytes(binary)
        changed=[i for i,(a,b) in enumerate(zip(original,code)) if a!=b]
        permitted={p-START+i for p,_ in patches for i in range(4)}
        require(set(changed)<=permitted,'non-MMIO preprocessing bytes changed')
        ins=donor.parse_disassembly(ROOT/'outputs/kernel-port/f303-oem-radar-re-20260904/objdump-dr.txt')
        require(not [i for i in ins if START<=i['address']<END and i['direct_target'] is not None and not START<=i['direct_target']<END],'branch escape')
        report={'schema':'openmitrastar.f330-preprocess-projection/v1','created_at':datetime.now(timezone.utc).isoformat(),
                'oem_sha256':EXPECTED,'original_function_bytes':len(original),'original_function_sha256':sha(original),
                'object_sha256':sha(binary),'projected_text_sha256':sha(code),'original_relocations':68,
                'new_mmio_address_relocations':2,'data_relocations':1,'changed_byte_offsets':changed,
                'permitted_operand_offsets':[p-START for p,_ in patches],'relocations':records,
                'algorithm_instructions_unchanged':True,'physical_mmio_performed':False,
                'backend_semantics':'Records a reset request; production must not commit until externally confirmed'}
        (out/'projection.json').write_text(json.dumps(report,indent=2)+'\n')
        return report

if __name__=='__main__':
    import sys
    target=Path(sys.argv[1]);target.mkdir(parents=True,exist_ok=False);print(json.dumps(emit(target),indent=2))
