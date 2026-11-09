"""Model exact AuC nomu post-start code copy, with forensic function entries."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from qdrv_fw_inspect import inspect_firmware

PIN='c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists() and sha(a.source)==PIN;a.output.mkdir(parents=True)
    raw=a.source.read_bytes();report=inspect_firmware(raw,source='pinned AuC nomu',cpu='auc')
    payload=bytearray(4096);names=b'\0';sections=[(0,)*10];records=[];regions=[]
    for segment in report.segments:
        if segment.virtual_address==0xffff0000:continue
        data=raw[segment.payload_offset:segment.payload_offset+segment.payload_size]
        if segment.index==7:
            replacement=report.segments[8];data=raw[replacement.payload_offset:replacement.payload_offset+replacement.payload_size]
            memory=len(data);authority='POSTSTART model: exact seg8 bytes copied63b3b0 toe50073b0 by original7404'
        else:memory=segment.memory_size;authority='paddr-first initial loader payload/BSS'
        no=len(names);name=f'.load{segment.index}';names+=name.encode()+b'\0';payload.extend(b'\0'*((-len(payload))%4));off=len(payload);payload.extend(data)
        flags=6 if segment.flags&1 else 3
        if data:sections.append((no,1,flags,segment.load_address,off,len(data),0,0,4,0));regions.append((segment.load_address,len(data),len(sections)-1))
        if memory>len(data):
            no=len(names);names+=f'.bss{segment.index}'.encode()+b'\0';sections.append((no,8,3,segment.load_address+len(data),0,memory-len(data),0,0,4,0))
        records.append({'index':segment.index,'address':hex(segment.load_address),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'authority':authority})
    functions={
        'om_auc_native_main_loop':(0xe5004abc,0x74),
        'om_auc_ipc_config_dispatch':(0xe500518c,0x6dc),
        'om_auc_ocs_suspend_command21_clause':(0xe50056f4,0x2a),
        'om_auc_management_fcs_enqueue':(0xe5000cf4,0x6c),
        'om_auc_m2a_ipc_irq':(0xe5005ab4,0x118),
        'om_auc_tx_done_management_flags':(0xe5001a50,0x8e),
        'om_auc_poststart_tqe_scheduler':(0xe50077c8,0x550),
    }
    symnames=b'\0';symbols=bytearray(16)
    for name,(address,size)in functions.items():
        target=next(index for begin,length,index in regions if begin<=address<begin+length)
        symbols.extend(struct.pack('<IIIBBH',len(symnames),address,size,0x12,0,target));symnames+=name.encode()+b'\0'
    payload.extend(b'\0'*((-len(payload))%4));symoff=len(payload);payload.extend(symbols)
    no=len(names);names+=b'.symtab\0';symindex=len(sections);sections.append((no,2,0,0,symoff,len(symbols),symindex+1,1,4,16))
    stroff=len(payload);payload.extend(symnames);no=len(names);names+=b'.strtab\0';sections.append((no,3,0,0,stroff,len(symnames),0,0,1,0))
    no=len(names);names+=b'.shstrtab\0';off=len(payload);payload.extend(names);sections.append((no,3,0,0,off,len(names),0,0,1,0));payload.extend(b'\0'*((-len(payload))%4));shoff=len(payload)
    payload.extend(b''.join(struct.pack('<10I',*s)for s in sections));payload[:52]=struct.pack('<16sHHIIIIIHHHHHH',raw[:16],2,93,1,0xe5004abc,0,shoff,0,52,32,0,40,len(sections),len(sections)-1)
    out=a.output/'auc-nomu-POSTSTART-ENTRIES-ANALYSIS-ONLY.elf';out.write_bytes(payload);assert sha(a.source)==PIN
    result={'status':'PASS_EXACT_NOMU_POSTSTART_CODECOPY_MODEL_WITH_FORENSIC_ENTRIES','source_sha256':PIN,'derived_sha256':sha(out),'hardware_accessed':False,'firmware_eligible':False,'regions':records,'functions':functions,'gp_from_boot':'0xe51010c8','limits':['A hypothesized poststart state from exact originalcopyinstructions; never runtime verification','Only seg8 copied toe50073b0; alternate exceptionseg6 overlay is not applied in this state','Symbols/sizes are forensic analysis hints; REA body ranges must independently validate','Native AuC custom opcode decode remains unqualified; instructions/pseudocode must retain limitations','No replacement of prior initial-map evidence or modification of OEMcarrier']}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'derived_sha256':result['derived_sha256']}))
if __name__=='__main__':main()
