"""Derive one exact MuC executable code window for offline REA only.

Original firmware stays unchanged. The derived ELF preserves machine/flags and
contains exact segment8 payload bytes at the recorded0xe0000 address. Other
memory regions, hardware state and functions are absent; never install this ELF.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from qdrv_fw_inspect import inspect_firmware


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


FUNCTIONS={
 'om_muc_setparams_dispatch':(0x11f14c,7148),
 'om_muc_nac_mode':(0x16548c,452),
 'om_muc_dynamic_sifs':(0x11f01c,0),
 'om_muc_duplicate_rts':(0x11ee48,0),
}


def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 source=a.source.read_bytes();source_sha=sha(a.source);assert source_sha=='71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4'
 report=inspect_firmware(source,source=str(a.source),cpu='muc');segment=report.segments[8]
 assert(segment.virtual_address,segment.payload_offset,segment.payload_size)==(0xe0000,131796,963131)
 code=source[segment.payload_offset:segment.payload_offset+segment.payload_size]
 assert all(segment.virtual_address<=addr<segment.virtual_address+len(code)for addr,_ in FUNCTIONS.values())
 a.output.mkdir(parents=True,exist_ok=False)
 names=b'\0'+b''.join(name.encode()+b'\0'for name in FUNCTIONS)
 syms=bytearray(16);cursor=1
 for name,(address,size)in FUNCTIONS.items():
  syms.extend(struct.pack('<IIIBBH',cursor,address,size,0x12,0,1));cursor+=len(name)+1
 shnames=b'\0.text\0.symtab\0.strtab\0.shstrtab\0';name_offsets={x:shnames.index(x.encode()+b'\0')for x in ['.text','.symtab','.strtab','.shstrtab']}
 payload=bytearray(0x1000);payload.extend(code)
 def align(n):
  payload.extend(b'\0'*((-len(payload))%n))
 align(4);symoff=len(payload);payload.extend(syms);stroff=len(payload);payload.extend(names);shstroff=len(payload);payload.extend(shnames);align(4);shoff=len(payload)
 headers=[(0,)*10,(name_offsets['.text'],1,6,segment.virtual_address,0x1000,len(code),0,0,4,0),(name_offsets['.symtab'],2,0,0,symoff,len(syms),3,1,4,16),(name_offsets['.strtab'],3,0,0,stroff,len(names),0,0,1,0),(name_offsets['.shstrtab'],3,0,0,shstroff,len(shnames),0,0,1,0)]
 payload.extend(b''.join(struct.pack('<10I',*h)for h in headers))
 original_flags=struct.unpack_from('<I',source,36)[0]
 payload[:52]=struct.pack('<16sHHIIIIIHHHHHH',source[:16],2,93,1,0x11f14c,52,shoff,original_flags,52,32,1,40,len(headers),4)
 payload[52:84]=struct.pack('<8I',1,0x1000,segment.virtual_address,segment.virtual_address,len(code),len(code),5,0x1000)
 target=a.output/'muc-CODE_WINDOW-ANALYSIS_ONLY-NOT_FIRMWARE.elf';target.write_bytes(payload)
 assert target.read_bytes()[0x1000:0x1000+len(code)]==code and sha(a.source)==source_sha
 result=dict(status='PASS_EXACT_MUC_CODE_WINDOW_DERIVATIVE',classification='ANALYSIS_ONLY_NEVER_LOAD_BOOT_PACKAGE_OR_FLASH',hardware_accessed=False,firmware_eligible=False,source_sha256=source_sha,source_unchanged=True,derived_sha256=sha(target),derived_bytes=target.stat().st_size,elf_flags_preserved=original_flags,machine_preserved=93,code_address=hex(segment.virtual_address),code_bytes=len(code),code_sha256=hashlib.sha256(code).hexdigest(),functions=FUNCTIONS,limits=['Onlyselectedcodewindow imported; hardwareMMIO/SRAM/globalaliases/notincluded.','Functionlabels are forensic hints from exactsource-decompilation/cases, notoriginalsymbols.','ELFflags0preserved; REAadmissionlane requires explicitfirmwaredecoder qualification.','Crosswindowcalls unresolved, no loader/hardwaretiming/emulation claim.'])
 (a.output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
