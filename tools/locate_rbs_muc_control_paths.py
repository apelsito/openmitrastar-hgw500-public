"""Boundedforensicliteralrefs andELFsegment map onpinnedMuC noHW."""
import json,re,struct,hashlib
from pathlib import Path
from qdrv_fw_inspect import inspect_firmware
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'work/rc1-radio-drivers-20260824-extract/openmitrastar-linux510-radio-drivers-product-rc1-20260824/radio5g/firmware/qtn_driver.qtn_ruby.0.bin';raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()=='71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4';r=inspect_firmware(raw,source=str(p),cpu='muc');code=r.segments[8];asm=(ROOT/'outputs/rea/rbs-muc-code-disassembly-20261022T235300Z-r1.txt').read_text().splitlines();rows=[]
for m in re.finditer(rb'[ -~]{7,}',raw):
 if not re.search(rb'(?i)\b(?:cac|radar|xmit|transmit|mgmt|host.*ioctl|dfs)\b',m.group()):continue
 seg=next((s for s in r.segments if s.payload_offset<=m.start()<s.payload_offset+s.payload_size),None)
 if not seg:continue
 addr=seg.virtual_address+m.start()-seg.payload_offset;word=struct.pack('<I',addr);half=struct.pack('<HH',addr>>16,addr&65535);window=raw[code.payload_offset:code.payload_offset+code.payload_size];hits=[code.virtual_address+x.start()for x in re.finditer(re.escape(half),window)];rows.append({'file_offset':hex(m.start()),'address':hex(addr),'text':m.group().decode()[:200],'code_literal_positions':[hex(x)for x in hits]})
print(json.dumps({'segments':[{'index':s.index,'vaddr':hex(s.virtual_address),'offset':s.payload_offset,'bytes':s.payload_size,'flags':s.flags}for s in r.segments],'strings':rows,'ELF_shoff':struct.unpack_from('<I',raw,32)[0],'ELF_shnum':struct.unpack_from('<H',raw,48)[0]},indent=2))
