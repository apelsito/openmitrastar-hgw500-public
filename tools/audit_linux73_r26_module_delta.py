"""Bound actual R24/R26 delta to clear/reset/loader/provider sources."""
import argparse,hashlib,json,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in('old','new','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--cross-prefix',required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 old=json.loads((a.old/'result.json').read_text());new=json.loads((a.new/'result.json').read_text());assert old['status'].startswith('PASS_PAIRED')and new['status'].startswith('PASS_PAIRED');rows=[]
 expected={'source/qdrv/qdrv_fw.o','source/qdrv/qdrv_auc.o','source/qdrv/qdrv_control.o','source/qdrv/qdrv_soc.o','providers/sram73/om73_sram_backend.o'}
 for lane in('a','b'):
  left=a.old/lane;right=a.new/lane;units=[p.relative_to(left).as_posix()for d in('source','providers')for p in(left/d).rglob('*.o')]
  changed=sorted(u for u in units if sha(left/u)!=sha(right/u));assert set(changed)==expected,changed
  modules=sorted(p.name for p in left.glob('*.ko'));changedmods=sorted(n for n in modules if sha(left/n)!=sha(right/n));assert changedmods==['om73_sram.ko','qdrv.ko'],changedmods
  parse=lambda text:{l.split()[-1]:l.split()[-2]for l in text.splitlines()if len(l.split())>=2}
  before=parse(subprocess.check_output([a.cross_prefix+'nm','-g',str(left/'qdrv.ko')],text=True));after=parse(subprocess.check_output([a.cross_prefix+'nm','-g',str(right/'qdrv.ko')],text=True));assert all(after.get(k)==v for k,v in before.items()if v!='U'),'oldqdrvdefinitionchanged'
  poolbefore=parse(subprocess.check_output([a.cross_prefix+'nm','-g',str(left/'om73_sram.ko')],text=True));poolafter=parse(subprocess.check_output([a.cross_prefix+'nm','-g',str(right/'om73_sram.ko')],text=True));assert all(poolafter.get(k)==v for k,v in poolbefore.items()),'oldpoolcontractchanged'
  rows.append({'lane':lane,'changed_C_objects':changed,'changed_modules':changedmods,'other_20_modules_identical':True,'old_public_symbols_and_types_preserved':True,'new_qdrv_symbols':sorted(k for k in after if k not in before),'new_pool_symbols':sorted(k for k in poolafter if k not in poolbefore)})
 same=all(old['input_pins'][k]==h for k,h in new['input_pins'].items()if k in old['input_pins']and'kernel-context/'in k);assert same
 result={'status':'PASS_ACTUAL_R24_R26_ONLY_FIVE_CLEAR_RESET_OBJECTS_TWO_MODULES_CHANGED','lanes':rows,'old_pair_sha256':sha(a.old/'result.json'),'new_pair_sha256':sha(a.new/'result.json'),'kernel_config_symvers_unchanged':same,'hardware_accessed':False,'firmware_eligible':False};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
