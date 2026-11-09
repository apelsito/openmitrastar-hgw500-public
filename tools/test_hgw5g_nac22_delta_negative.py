"""Seven in-memory tamperchecks for actualNAC22 residualauditor."""
import argparse
import copy
import json
from pathlib import Path
from qualify_f370_qdrv_module import Elf
from qualify_hgw5g_nac22_closure import audit

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);old=Elf(a.parent);new=Elf(a.candidate);audit(old,copy.deepcopy(new));rows=[]
 for kind in ['function','padding','data','table','relocation','symbol','diagnostic']:
  e=copy.deepcopy(new)
  def byte(sec,offset):
   x=bytearray(e.byname[sec]['data']);x[offset]^=1;e.byname[sec]['data']=bytes(x)
  if kind=='function':s=next(s for s in e.syms if s['name']=='ieee80211_setmode'and s['type']==2);byte(e.symsection(s),s['value'])
  elif kind=='padding':byte('.init.text',0)
  elif kind=='data':byte('.data.once',0)
  elif kind=='table':s=next(s for s in e.syms if s['name']=='ieee80211_priv_args');byte('.rodata',s['value'])
  elif kind=='relocation':r=next(r for r in e.relas if e.syms[r['symbol']]['name']=='printk'and r['section']=='.text'and r['offset']<45000);r['addend']+=4
  elif kind=='symbol':s=next(s for s in e.syms if s['name']=='ieee80211_setmode'and s['type']==2);s['size']+=2
  elif kind=='diagnostic':s=next(s for s in e.syms if s['name']=='ieee80211_param_from_qdrv'and s['type']==2);byte(e.symsection(s),s['value']+112)
  try:audit(old,e)
  except(AssertionError,ValueError)as ex:rows.append(dict(case=kind,rejected=True,reason=str(ex)))
  else:rows.append(dict(case=kind,rejected=False))
 assert all(r['rejected']for r in rows)
 result=dict(status='PASS_SEVEN_NAC22_NEGATIVE_AUDIT_CASES',cases=7,hardware_accessed=False,files_modified=False,rows=rows);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
