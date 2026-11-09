"""Construct an immutable AuC nomu analysis ELF, never eligible for loading."""
import argparse
import hashlib
import json
import struct
from dataclasses import asdict
from pathlib import Path
from qdrv_fw_inspect import inspect_firmware

PIN='c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists() and sha(args.source)==PIN
    args.output.mkdir(parents=True)
    raw=args.source.read_bytes()
    firmware=inspect_firmware(raw,source='pinned AuC nomu owner carrier',cpu='auc')
    payload=bytearray(4096); names=b'\0'; sections=[(0,)*10]; records=[]
    allocated=[]
    for segment in firmware.segments:
        data=raw[segment.payload_offset:segment.payload_offset+segment.payload_size]
        if segment.virtual_address==0xffff0000:
            assert data.startswith(b'FWINFO')
            name='.fwinfo'; address=0; flags=0; memory=segment.payload_size
        else:
            name=f'.load{segment.index}'
            address=segment.load_address
            flags=6 if segment.flags&1 else 3
            memory=segment.memory_size
            allocated.append((address,address+memory,segment.index))
        nameoff=len(names);names+=name.encode()+b'\0'
        payload.extend(b'\0'*((-len(payload))%4));offset=len(payload);payload.extend(data)
        if data:
            sections.append((nameoff,1,flags,address,offset,len(data),0,0,4,0))
        if memory>len(data):
            bssname=f'.bss{segment.index}';no=len(names);names+=bssname.encode()+b'\0'
            sections.append((no,8,3,address+len(data),0,memory-len(data),0,0,4,0))
        records.append(asdict(segment)|{'section_address':hex(address),'payload_preserved':True,'fwinfo_not_loaded':segment.virtual_address==0xffff0000,'bss_model':'loader zero-fill NOBITS; no live-runtime state claim'})
    for n,(begin,end,index) in enumerate(allocated):
        for ob,oe,oi in allocated[n+1:]:assert end<=ob or oe<=begin,(index,oi)
    no=len(names);names+=b'.shstrtab\0';offset=len(payload);payload.extend(names)
    sections.append((no,3,0,0,offset,len(names),0,0,1,0))
    payload.extend(b'\0'*((-len(payload))%4));shoff=len(payload)
    payload.extend(b''.join(struct.pack('<10I',*section)for section in sections))
    payload[:52]=struct.pack('<16sHHIIIIIHHHHHH',raw[:16],2,93,1,firmware.entry_point,0,shoff,0,52,32,0,40,len(sections),len(sections)-1)
    target=args.output/'auc-nomu-LOADED-IMAGE-ANALYSIS-ONLY.elf';target.write_bytes(payload)
    assert sha(args.source)==PIN
    result={'status':'PASS_EXACT_AUC_NOMU_PADDR_FIRST_PAYLOAD_AND_BSS_ANALYSIS_ONLY','hardware_accessed':False,'firmware_eligible':False,'source_sha256':PIN,'derived_sha256':sha(target),'entry':hex(firmware.entry_point),'segments':records,'limits':['FWINFO metadata represented as nonallocated section and never load target','paddr nonzero wins before vaddr; segments6/8 loadcopy at63bee4/63b3b0 must not overlay nativeIMEMe5000000/e50073b0','NOBITS encodes loader zero-fill only; boot-created callbacks/sharedpointers are unknown','Processor-to-host bus address aliases are not independent runtime proof','No binary bytes changed; standalone artifact is for static analysis only']}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'derived_sha256':result['derived_sha256'],'segments':len(records),'entry':result['entry']}))

if __name__=='__main__':main()
