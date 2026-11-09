"""Compare actual R22/R23 pairs, require only the bounded loader unit to change."""
import argparse,hashlib,json,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in('old','new','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--cross-prefix',required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 old=json.loads((a.old/'result.json').read_text());new=json.loads((a.new/'result.json').read_text());assert old['status'].startswith('PASS_PAIRED')and new['status'].startswith('PASS_PAIRED');rows=[]
 for lane in('a','b'):
  left=a.old/lane;right=a.new/lane
  units=[p.relative_to(left).as_posix()for d in('source','providers')for p in(left/d).rglob('*.o')]
  changed=[u for u in units if sha(left/u)!=sha(right/u)];assert changed==['source/qdrv/qdrv_fw.o'],changed
  modules=[p.name for p in left.glob('*.ko')];changedmods=sorted(n for n in modules if sha(left/n)!=sha(right/n));assert changedmods==['qdrv.ko'],changedmods
  oldnm=subprocess.check_output([a.cross_prefix+'nm','-g',str(left/'qdrv.ko')],text=True)
  newnm=subprocess.check_output([a.cross_prefix+'nm','-g',str(right/'qdrv.ko')],text=True)
  parse=lambda text:{l.split()[-1]:l.split()[-2]for l in text.splitlines()if len(l.split())>=2}
  assert parse(oldnm)==parse(newnm),'Globalsymboltypeornamechanged'
  before=subprocess.check_output([a.cross_prefix+'nm','-S',str(left/'source/qdrv/qdrv_fw.o')],text=True)
  after=subprocess.check_output([a.cross_prefix+'nm','-S',str(right/'source/qdrv/qdrv_fw.o')],text=True)
  (a.output/(lane+'-r22-fw-nm.txt')).write_text(before);(a.output/(lane+'-r23-fw-nm.txt')).write_text(after)
  sections={}
  for module in modules:
   differences=[]
   for name in('.text','.rodata','.data','.bss','.modinfo'):
    oldbin=a.output/(lane+'-'+module+'-old-'+name[1:]);newbin=a.output/(lane+'-'+module+'-new-'+name[1:])
    for path,target in((left/module,oldbin),(right/module,newbin)):
     subprocess.run([a.cross_prefix+'objcopy','--dump-section',name+'='+str(target),str(path)],check=True,capture_output=True)
    if oldbin.exists()or newbin.exists():
     if not oldbin.exists()or not newbin.exists()or oldbin.read_bytes()!=newbin.read_bytes():differences.append(name)
   sections[module]=differences
  assert all(not v for k,v in sections.items()if k!='qdrv.ko')
  rows.append({'lane':lane,'changed_C_objects':changed,'changed_modules':changedmods,'global_qdrv_symbols_and_types_unchanged':True,'section_deltas':sections})
 result={'status':'PASS_ACTUAL_R22_R23_ONLY_QDRV_FW_OBJECT_AND_QDRV_MODULE_CHANGED','lanes':rows,'old_pair_sha256':sha(a.old/'result.json'),'new_pair_sha256':sha(a.new/'result.json'),'kernel_config_and_symvers_unchanged':all(old['input_pins'][k]==h for k,h in new['input_pins'].items()if k in old['input_pins']and('kernel-context/'in k)),'hardware_accessed':False,'firmware_eligible':False};assert result['kernel_config_and_symvers_unchanged'];(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
