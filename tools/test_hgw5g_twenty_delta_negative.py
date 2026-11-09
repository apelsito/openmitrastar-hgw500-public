"""Seven parsed-ELF tamper counterexamples for strict typed20 deltaaudit.

Mutations are in-memory parsedcopies, never firmware/module files. Each must be
rejected by the real fullresidual audit; intentionalbody fixtures remain separate.
"""
import argparse
import copy
import json
from pathlib import Path

from qualify_f370_qdrv_module import Elf
from qualify_hgw5g_twenty_typed_closure import audit_wlan

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 old=Elf(a.parent);baseline=Elf(a.candidate);audit_wlan(old,baseline);rows=[]
 cases=['unrelated_function_code','unowned_section_padding','allocated_data','readonly_table_prefix','external_relocation','symbol_size','diagnostic_extra_instruction']
 for kind in cases:
  elf=copy.deepcopy(baseline)
  def byte(section,offset):
   x=bytearray(elf.byname[section]['data']);x[offset]^=1;elf.byname[section]['data']=bytes(x)
  if kind=='unrelated_function_code':
   s=next(s for s in elf.syms if s['name']=='ieee80211_setmode'and s['type']==2);byte(elf.symsection(s),s['value'])
  elif kind=='unowned_section_padding':byte('.init.text',0)
  elif kind=='allocated_data':byte('.data.once',0)
  elif kind=='readonly_table_prefix':
   s=next(s for s in elf.syms if s['name']=='ieee80211_priv_args');byte('.rodata',s['value'])
  elif kind=='external_relocation':
   r=next(r for r in elf.relas if elf.syms[r['symbol']]['name']=='printk'and r['section']=='.text'and r['offset']<45000);r['addend']+=4
  elif kind=='symbol_size':
   s=next(s for s in elf.syms if s['name']=='ieee80211_setmode'and s['type']==2);s['size']+=2
  elif kind=='diagnostic_extra_instruction':
   s=next(s for s in elf.syms if s['name']=='ieee80211_chan2mode'and s['type']==2);byte(elf.symsection(s),s['value']+60)
  try:audit_wlan(old,elf)
  except (AssertionError,ValueError)as ex:rows.append(dict(case=kind,rejected=True,reason=str(ex)))
  else:rows.append(dict(case=kind,rejected=False))
 assert all(r['rejected']for r in rows),rows
 result=dict(status='PASS_SEVEN_NEGATIVE_TYPED_DELTA_CASES',cases=7,hardware_accessed=False,files_modified=False,rows=rows)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
