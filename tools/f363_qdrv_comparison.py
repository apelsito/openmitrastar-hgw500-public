"""Narrow proof for the WARN_ON_ONCE source-line operand in unchanged exit code."""
from pathlib import Path
import hashlib,struct
from elftools.elf.elffile import ELFFile
from test_f355_lifetime import extract
def warn_line_metadata(left_module,right_module,left_source,right_source):
 name='qdrv_wlan_exit';rows=[]
 left_body=extract(Path(left_source).read_text(),name);right_body=extract(Path(right_source).read_text(),name)
 if left_body!=right_body:raise ValueError('wlan exit source changed')
 for module,source in ((left_module,left_source),(right_module,right_source)):
  text=Path(source).read_text();body=extract(text,name);start=text.index(body);position=text.index('WARN_ON_ONCE(!dma_dev)',start)
  if position>=start+len(body):raise ValueError('wrong WARN site')
  line=text.count('\n',0,position)+1
  with Path(module).open('rb') as f:
   elf=ELFFile(f);symbols=elf.get_section_by_name('.symtab');symbol=symbols.get_symbol_by_name(name)[0]
   section=elf.get_section(symbol['st_shndx']);begin=symbol['st_value'];size=symbol['st_size'];raw=bytearray(section.data()[begin:begin+size]);warn=[]
   for reloc in elf.iter_sections():
    if reloc['sh_type']!='SHT_RELA' or reloc['sh_info']!=symbol['st_shndx']:continue
    for r in reloc.iter_relocations():
     off=r['r_offset']-begin
     if not 0<=off<size:continue
     if symbols.get_symbol(r['r_info_sym']).name=='warn_slowpath_fmt':warn.append(off)
     raw[off:off+4]=b'\0'*min(4,size-off)
   if len(warn)!=1:raise ValueError('ambiguous exit warning relocation')
   operand=warn[0]-16
   if raw[operand-4:operand]!=bytes.fromhex('0a21800f'):raise ValueError('warning line is not mov r1,limm')
   hi,lo=struct.unpack_from('<HH',raw,operand);value=(hi<<16)|lo
   if value!=line:raise ValueError('warning immediate does not equal source line')
   rows.append({'line':line,'operand':operand,'size':size,'raw':raw})
 if rows[0]['size']!=rows[1]['size'] or rows[0]['operand']!=rows[1]['operand']:raise ValueError('exit layout changed')
 before,after=rows[0]['raw'],rows[1]['raw'];differences=[i for i,(a,b) in enumerate(zip(before,after)) if a!=b]
 offset=rows[0]['operand']
 if not differences or any(not offset<=i<offset+4 for i in differences):raise ValueError('exit changed beyond warning line')
 before[offset:offset+4]=after[offset:offset+4]=b'\0'*4
 if before!=after:raise ValueError('exit executable bytes differ')
 return {'function':name,'source_body_sha256':hashlib.sha256(left_body.encode()).hexdigest(),'bytes':rows[0]['size'],'baseline_line':rows[0]['line'],'temperature_line':rows[1]['line'],'line_operand_offset':offset,'changed_byte_offsets':differences,'all_other_relocation_normalized_bytes_equal':True,'normalized_without_line_sha256':hashlib.sha256(before).hexdigest(),'reason':'WARN_ON_ONCE __LINE__ only; no teardown behavior changed'}
