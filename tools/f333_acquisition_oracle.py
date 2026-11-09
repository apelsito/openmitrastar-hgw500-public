"""Project original raw/ZC acquisition loops into private QEMU wrappers.

Only physical-address operands are rebound to fixture RAM and original ELF
relocations are applied. Original arithmetic and control-flow bytes survive.
"""
from pathlib import Path
import json,struct
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from f328_oem_classifier_projection import OEM,EXPECTED,sha,require

RAW=(0x3e08,0x3f28)
ZC=(0x3f66,0x40fe)
PATCHES={
 0x3e0c:(0xe6091570,'f333_reg_current'),0x3e14:(0xe609156c,'f333_reg_start'),
 0x3e56:(0x19bff000,'f333_negative_low'),0x3e5e:(0x19bfec00,'f333_negative_high'),
 0x3e76:(0xe6401400,'f333_high_bank'),0x3e7e:(0xe6401000,'f333_low_bank'),
 0x3f6a:(0xe6091570,'f333_reg_current'),0x3f72:(0xe609156c,'f333_reg_start'),
 0x3f94:(0xe6091530,'f333_reg_chmem'),0x3fb2:(0x19c00000,'f333_negative_zc'),
 0x4022:(0xe6400dff,'f333_zc_valid_end'),0x40b8:(0xe6400fff,'f333_zc_end'),
}
def me(value):return struct.pack('<I',((value&0xffff)<<16)|(value>>16))
def emit(out):
    require(sha(OEM.read_bytes())==EXPECTED,'OEM hash mismatch')
    with OEM.open('rb') as stream:
        elf=ELFFile(stream);sections=list(elf.iter_sections());symtab=elf.get_section_by_name('.symtab')
        text=elf.get_section_by_name('.text').data();records={};assembly=[]
        for name,(start,end) in [('raw',RAW),('zc',ZC)]:
            original=text[start:end];data=bytearray(original);relocations=[]
            for position,(value,symbol) in PATCHES.items():
                if not start<=position<end:continue
                require(data[position-start:position-start+4]==me(value),'physical operand changed '+hex(position))
                data[position-start:position-start+4]=b'\0'*4
                relocations.append((position-start,symbol,0,'physical address'))
            original_relocs=0
            for sec in sections:
                if not isinstance(sec,RelocationSection) or sections[sec['sh_info']].name!='.text':continue
                for r in sec.iter_relocations():
                    pos=int(r['r_offset'])
                    if not start<=pos<end:continue
                    require(int(r['r_info_type'])==27,'unsupported relocation')
                    s=symtab.get_symbol(r['r_info_sym']);idx=s['st_shndx'];value=int(s['st_value'])+int(r['r_addend'])
                    if idx==6:symbol='f333_fake_bss';addend=value
                    elif idx==31:symbol='f333_oem_strings';addend=value
                    elif idx==1:
                        require(start<=value<end,'slice code escape');symbol='f333_'+name+'_body';addend=value-start
                    elif idx=='SHN_UNDEF' and s.name=='printk':symbol='f333_oracle_log';addend=0
                    else:raise ValueError((s.name,idx))
                    relocations.append((pos-start,symbol,addend,'original ELF relocation'));original_relocs+=1
            require(original_relocs==(7 if name=='raw' else 19),'slice relocation count changed')
            (out/(name+'-slice.bin')).write_bytes(data)
            body='f333_'+name+'_body'
            assembly+=['.section .text,"ax",@progbits','.balign 4','.global f333_oracle_'+name,'.type f333_oracle_'+name+',@function','f333_oracle_'+name+':']
            if name=='raw':assembly+=['st.aw blink,[sp,-8]','st r22,[sp,4]']
            else:
                assembly+=['st.aw blink,[sp,-40]']+['st r%d,[sp,%d]'%(r,(r-12)*4) for r in range(13,22)]
            if start%4==2:assembly+=['nop_s']
            assembly += [body+':','.incbin "'+(name+'-slice.bin')+'"']
            for off,symbol,addend,_ in relocations:assembly+=['.reloc '+body+'+'+str(off)+', R_ARC_32_ME, '+symbol+'+'+str(addend)]
            if name=='raw':assembly+=['mov r0,r22','ld r22,[sp,4]','ld blink,[sp,0]','add sp,sp,8','j [blink]']
            else:
                assembly+=['mov r0,r21','mov r2,f333_zc_next','st r15,[r2]']+['ld r%d,[sp,%d]'%(r,(r-12)*4) for r in range(13,22)]+['ld blink,[sp,0]','add sp,sp,40','j [blink]']
            assembly+=['.size f333_oracle_'+name+',.-f333_oracle_'+name]
            changed=[i for i,(a,b) in enumerate(zip(original,data)) if a!=b]
            permitted={p-start+i for p in PATCHES if start<=p<end for i in range(4)}
            require(set(changed)<=permitted,'algorithm bytes changed')
            records[name]={'start':hex(start),'end':hex(end),'bytes':len(original),'original_sha256':sha(original),
                           'projected_sha256':sha(data),'changed_byte_offsets':changed,'relocations':relocations,'original_relocations':original_relocs}
        (out/'oem-strings.bin').write_bytes(elf.get_section_by_name('.rodata.str1.4').data())
        assembly+=['.section .rodata,"a",@progbits','.global f333_oem_strings','f333_oem_strings:','.incbin "oem-strings.bin"']
        (out/'oracle.S').write_bytes(('\n'.join(assembly)+'\n').encode())
        (out/'projection.json').write_text(json.dumps({'schema':'openmitrastar.f333-acquisition-slices/v1','oem_sha256':EXPECTED,'slices':records,'hardware_actions':False},indent=2)+'\n')
        return records
