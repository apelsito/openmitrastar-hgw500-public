"""Record the reviewed nine-function F364 diagnostic/link-layout delta; no build."""
from pathlib import Path
import difflib,hashlib,json,re,subprocess
from elftools.elf.elffile import ELFFile
from prepare_f344_csa_policy import closing
import f334_qdrv_contract as qc
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/workspace/OpenMitraStar-build/f364/f364-lifetime-20260921T204704Z')
LEFT=Path('/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/a/temperature/qdrv/qdrv.ko')
RIGHT=OUT/'a/qdrv/qdrv.ko'
LQ=ROOT/'work/linux510-radio-port/quantenna-f363-temperature/qdrv'
RQ=ROOT/'work/linux510-radio-port/quantenna-f364-lifetime/qdrv'
SITES={
 'qdrv_command_dump':('qdrv_control.c',[]),
 'qdrv_command_rifs':('qdrv_control.c',[(2202,2204,'qtn_rifs_mode_enable'),(2204,2206,'qtn_rifs_mode_disable')]),
 'qdrv_command_start_block':('qdrv_control.c',[(778,780,'BUG_ON'),(779,781,'BUG_ON'),(800,802,'BUG_ON')]),
 'qdrv_control_txbf_pkt_send':('qdrv_control.c',[(3102,3104,'WARN_ON_ONCE')]),
 'qdrv_hostlink_alloc_coherent':('qdrv_hostlink.c',[(350,351,'WARN_ON_ONCE')]),
 'qdrv_hostlink_free_coherent_now':('qdrv_hostlink.c',[(413,414,'WARN_ON_ONCE')]),
 'qdrv_send_ioctl_owned':('qdrv_hostlink.c',[(178,179,'KASSERT')]),
 'qdrv_wlan_auth_state_change':('qdrv_wlan.c',[(5907,5908,'KASSERT'),(5920,5921,'KASSERT'),(5931,5932,'KASSERT')]),
 'qdrv_wlan_get_ocs_frame':('qdrv_wlan.c',[(1090,1091,'topaz_hbm_get_payload_virt')]),
}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def body(text,name):
 m=re.search(r'\b'+re.escape(name)+r'\([^;{}]*\)\s*\{',text);assert m,name
 return text[text.rfind('\n',0,m.start())+1:closing(text,m.start())+1]
def main():
 left,right=qc.normalized_functions(LEFT),qc.normalized_functions(RIGHT);items={};diffs=[]
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-objdump')
 for name,(file,sites) in SITES.items():
  a=(LQ/file).read_text();b=(RQ/file).read_text();assert body(a,name)==body(b,name),name
  for old,new,token in sites:assert token in a.splitlines()[old-1] and token in b.splitlines()[new-1],(name,old,new)
  rows=[]
  for path in (LEFT,RIGHT):
   text=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e',tc,'-dr','--disassemble='+name,linux(path)],capture_output=True,check=True).stdout.decode();asm=[]
   for line in text.splitlines():
    if not re.match(r'^\s*[0-9a-f]+:',line):continue
    tail=line.split(':',1)[1]
    if 'R_ARC_' in tail:continue
    pieces=tail.split('\t')
    if len(pieces)<3:continue
    asm.append(re.sub(r'\b[0-9a-f]+\s+<([^>]+)>',r'<\1>','\t'.join(pieces[2:]).strip())+'\n')
   rows.append(asm)
  diffs.append('FUNCTION '+name+'\n'+''.join(difflib.unified_diff(*rows,fromfile='F363',tofile='F364',n=3)))
  items[name]={'source_file':file,'source_body_sha256':hashlib.sha256(body(a,name).encode()).hexdigest(),
   'baseline':left[name],'candidate':right[name],'diagnostic_line_sites':[{'baseline':old,'candidate':new,'source_macro':token} for old,new,token in sites],
   'classification':'ELF_STATIC_OBJECT_OFFSET_ONLY' if not sites else 'SOURCE_LINE_DIAGNOSTICS_AND_COMPILER_ENCODING_ONLY',
   'reviewed_disassembly':True}
 assert body((LQ/'qdrv_control.c').read_text(),'qdrv_dump_hwreg')==body((RQ/'qdrv_control.c').read_text(),'qdrv_dump_hwreg')
 refs=[]
 for path,indices in ((LEFT,[170,171]),(RIGHT,[158,159])):
  with path.open('rb') as f:
   e=ELFFile(f);sy=e.get_section_by_name('.symtab');s=sy.get_symbol_by_name('qdrv_command_dump')[0]
   rels=[r for sec in e.iter_sections() if sec['sh_type']=='SHT_RELA' and sec['sh_info']==s['st_shndx'] for r in sec.iter_relocations() if r['r_offset']-s['st_value']==456]
   assert len(rels)==1;r=rels[0];target=sy.get_symbol(r['r_info_sym']);objects=[]
   for index in indices:
    address=target['st_value']+r['r_addend']+4*index
    matches=[v for v in sy.iter_symbols() if v['st_shndx']==target['st_shndx'] and v['st_info']['type']=='STT_OBJECT' and v['st_value']<=address<v['st_value']+v['st_size']]
    assert len(matches)==1;obj=matches[0];assert obj.name.startswith('sets.') and obj['st_size']==16
    objects.append({'symbol':obj.name,'field_offset':address-obj['st_value'],'scaled_load_index':index})
   assert [x['field_offset'] for x in objects]==[4,8];refs.append(objects)
 items['qdrv_command_dump']['static_object_members']={'baseline':refs[0],'candidate':refs[1],'members':['set_num','buf1_num'],
  'unchanged_inlined_helper_source_sha256':hashlib.sha256(body((LQ/'qdrv_control.c').read_text(),'qdrv_dump_hwreg').encode()).hexdigest(),
  'load_instruction_offsets':[460,516,538,674,678,698]}
 diff=OUT/'reviewed-nonfunctional-delta.diff';diff.write_text('\n'.join(diffs))
 report={'schema':'openmitrastar.f364-nonfunctional-delta-review/v1','status':'PASS_REVIEWED_NARROW_NONFUNCTIONAL_DELTA',
  'method':'Full normalized ARC disassembly diff reviewed, exact source bodies, diagnostic source-line sites and ELF-resolved static object members; no rebuild',
  'baseline_module_sha256':sha(LEFT),'candidate_module_sha256':sha(RIGHT),'functions':items,
  'disassembly_diff':{'path':str(diff),'sha256':sha(diff)},'hardware_actions':False}
 path=ROOT/'work/kernel-port/versions/f364-lifetime-integration/reviewed-nonfunctional-delta.json'
 with path.open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'path':str(path),'sha256':sha(path),'candidate_sha256':sha(RIGHT),'classified_functions':len(items)},indent=2))
if __name__=='__main__':main()
