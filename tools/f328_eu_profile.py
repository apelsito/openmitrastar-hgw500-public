"""Derive the OEM EU detect_cfg bytes from its straight-line initializer.

This is an instruction/data audit, not execution of radar_start or its MMIO.
Each store retains the exact original instruction address in the report.
"""
import ctypes
import gzip
import json
import re
from pathlib import Path
from elftools.elf.elffile import ELFFile
import f315_oem_radar_oracle as donor
from f328_oem_classifier_projection import OEM,ROOT,EXPECTED,sha,require

def derive(out):
    raw=OEM.read_bytes();require(sha(raw)==EXPECTED,'OEM binary provenance mismatch')
    config=(ROOT/'outputs/kernel-port/live-kernel-2.6.35.12.config').read_bytes()
    packed=(ROOT/'outputs/kernel-port/live-proc-config.gz').read_bytes()
    require(gzip.decompress(packed)==config,'OEM config gzip evidence mismatch')
    require(sha(config)=='38ceefd183703beb82e7f8de915082c19fd0febc89c5ee9b92a3ffd3ee4e9ea2','OEM config provenance mismatch')
    require(re.findall(rb'^CONFIG_HZ=(\d+)$',config,re.M)==[b'200'],'OEM HZ identity mismatch')
    parsed=donor.parse_elf(OEM)
    instructions=donor.parse_disassembly(ROOT/'outputs/kernel-port/f303-oem-radar-re-20260904/objdump-dr.txt')
    rels=[r for r in parsed['relocations'] if r['target_section']=='.text']
    by_instruction={}
    for index,inst in enumerate(instructions):
        next_address=instructions[index+1]['address'] if index+1<len(instructions) else inst['address']+12
        by_instruction[inst['address']]=[r for r in rels if inst['address']<=r['offset']<next_address]
    header=(ROOT/'work/sources/Quantenna-GPL/drivers/radar/detect.h').read_text()
    block=header.split('/* configuration */',1)[1].split('} detect_cfg_t;',1)[0].split('typedef struct {',1)[1]
    block=re.sub(r'/\*.*?\*/','',block,flags=re.S)
    fields=[]
    for typ,name,count in re.findall(r'\b(u8|bool|unsigned|int|long|char)\s+(\w+)(?:\[(\d+)\])?\s*;',block):
        ctype={'u8':ctypes.c_uint8,'bool':ctypes.c_uint8,'unsigned':ctypes.c_uint32,
               'int':ctypes.c_int32,'long':ctypes.c_int32,'char':ctypes.c_char}[typ]
        fields.append((name,ctype*int(count) if count else ctype))
    class Config(ctypes.LittleEndianStructure): _fields_=fields
    require(ctypes.sizeof(Config)==300,'OEM config layout mismatch')
    cfg=bytearray(300);regs={'r5':0,'r13':1};stores=[]
    def value(token):
        token=token.strip()
        if token in regs: return regs[token]
        return int(token,0)
    def apply(inst):
        m,oper,pc=inst['mnemonic'],inst['operands'],inst['address']
        r=by_instruction[pc];require(len(r)<=1,'ambiguous instruction relocation')
        relocation=r[0] if r else None
        if m in ('mov','mov_s'):
            dst,src=oper.split(',')
            regs[dst]=(relocation['symbol_section_index'],relocation['symbol_value']+relocation['addend']) if relocation else value(src)
        elif m in ('st','stb'):
            match=re.fullmatch(r'([^,]+),\[([^\]]+)\]',oper);require(match,inst)
            src,addr=match.groups();amount=value(src)
            if relocation:
                require(relocation['symbol_section_index']==6,'non-BSS initializer write')
                location=relocation['symbol_value']+relocation['addend']
            else:
                base,delta=addr.split(',');section,location=regs[base];require(section==6,'non-BSS pointer write')
                location+=int(delta,0)
            offset=location-0x12a4;size=1 if m=='stb' else 4
            require(0<=offset and offset+size<=len(cfg),(inst,hex(location)))
            require(isinstance(amount,int),'unknown initializer value')
            cfg[offset:offset+size]=amount.to_bytes(size,'little')
            stores.append({'pc':hex(pc),'offset':offset,'bytes':size,'value':amount})
        elif m=='b': require(pc==0x696e and inst['direct_target']==0x7000,'unexpected initializer branch')
        else: raise ValueError(inst)
    for inst in instructions:
        if 0x6662<=inst['address']<0x6972 or 0x700c<=inst['address']<0x702c: apply(inst)
    with OEM.open('rb') as stream:
        strings=ELFFile(stream).get_section_by_name('.rodata.str1.4').data()
        region=strings[0x254c:].split(b'\0',1)[0];require(region==b'EU','EU string mismatch')
    offset=Config.region_str.offset
    cfg[offset:offset+3]=b'EU\0'
    stores.append({'pc':'0x7008 sprintf, argument0x6914','offset':offset,'bytes':3,'value':'EU\\0'})
    # Audit subsequent config references: only one direct config store follows
    # detect_init. Its value is loaded from cfg.win_per_pulse and multiplied by4.
    post=[]
    for inst in instructions:
        if not 0x7030<=inst['address']<0x75b8: continue
        for r in by_instruction[inst['address']]:
            if r['symbol_section_index']==6 and 0x12a4<=r['addend']<0x13d0:
                post.append({'instruction':inst,'relocation':r})
    writes=[p for p in post if p['instruction']['mnemonic'] in ('st','stb','sth')]
    require(len(writes)==1 and writes[0]['instruction']['address']==0x7252,'post-init profile write drift')
    require(writes[0]['relocation']['addend']==0x1394,'post-init field mismatch')
    selected={i['address']:i for i in instructions}
    require(selected[0x71cc]['mnemonic']=='ld' and selected[0x71cc]['operands']=='r4,[0]','window load drift')
    require(by_instruction[0x71cc][0]['addend']==0x1390,'window source drift')
    require(selected[0x721e]['mnemonic']=='asl' and selected[0x721e]['operands']=='r5,r4,0x2','window scale drift')
    width=int.from_bytes(cfg[0x1390-0x12a4:0x1394-0x12a4],'little')
    cfg[0x1394-0x12a4:0x1398-0x12a4]=(width*4).to_bytes(4,'little')
    stores.append({'pc':'0x71cc load ->0x721e shift ->0x7252 store','offset':0x1394-0x12a4,'bytes':4,'value':width*4})
    view=Config.from_buffer_copy(cfg)
    values={name:(getattr(view,name).decode() if isinstance(getattr(view,name),bytes) else int(getattr(view,name))) for name,_ in fields}
    report={'schema':'openmitrastar.f328-oem-eu-profile/v1','oem_sha256':EXPECTED,
            'cfg_bytes':300,'control_block_bytes':0x89c,'cfg_sha256':sha(cfg),
            'legacy_hz':200,'oem_config_sha256':sha(config),'oem_config_gzip_sha256':sha(packed),
            'profile':'EU branch in exact radar_start, including later cfg store',
            'code_not_executed':True,'hardware_not_accessed':True,'stores':stores,
            'fields':values,'field_offsets':{n:getattr(Config,n).offset for n,_ in fields},
            'post_detect_init_cfg_refs':post,
            'limitations':['Read-only code/data reconstruction; independent target runtime oracle equivalence not yet proved',
                           'No post-detection polling-worker filters, OCAC control changes, or RF acceptance',
                           'Legacy HZ200 is established; six EU fixtures do not exercise LSR or timer expiry']}
    (out/'eu-profile-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'eu-profile.bin').write_bytes(cfg)
    (out/'eu-profile.h').write_text('static const unsigned char f328_eu_cfg[300]={\n'+','.join(str(b) for b in cfg)+'\n};\n')
    print(json.dumps({'status':'EU_PROFILE_DERIVED_FROM_EXACT_CODE','bytes':300,'sha256':sha(cfg),
                      'lsrDetectEnable':values['lsrDetectEnable'],'stores':len(stores)}))
    return report

if __name__=='__main__':
    import sys
    derive(Path(sys.argv[1]))
