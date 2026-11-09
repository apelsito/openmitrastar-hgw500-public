"""Parsed in-memory tamper tests for both actual SOURCE25 residual auditors."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from qualify_f370_qdrv_module import Elf
from audit_hgw5g_coc25_controlled_modules import audit

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--control',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);rows=[];pins={str(Path(__file__)):sha(__file__),str(Path(__file__).with_name('audit_hgw5g_coc25_controlled_modules.py')):sha(Path(__file__).with_name('audit_hgw5g_coc25_controlled_modules.py'))}
 for component in('qdrv','wlan'):
  op=a.control/component/(component+'.ko');np=a.candidate/component/(component+'.ko');pins[str(op)]=sha(op);pins[str(np)]=sha(np);old,new=Elf(op),Elf(np);audit(old,copy.deepcopy(new),component)
  kinds=('function','anonymous','data','relocation','symbol','diagnostic')if component=='wlan'else('function','anonymous','data','relocation','symbol')
  for kind in kinds:
   e=copy.deepcopy(new)
   def byte(sec,pos):z=bytearray(e.byname[sec]['data']);z[pos]^=1;e.byname[sec]['data']=bytes(z)
   if kind=='function':s=next(s for s in e.syms if s['type']==2 and s['name']==('ieee80211_setmode'if component=='wlan'else'qdrv_hostlink_msg_cmd'));byte(e.symsection(s),s['value'])
   elif kind=='anonymous':
    fs=sorted([s for s in e.syms if s['type']==2 and s['size']and e.symsection(s)=='.text'],key=lambda s:s['value']);pos=0
    for s in fs:
     if s['value']-pos>20:byte('.text',pos+8);break
     pos=max(pos,s['value']+s['size'])
    else:raise AssertionError('anonymous interval absent')
   elif kind=='data':sec=next(x for x in('.data.once','.data','.rodata')if x in e.byname and e.byname[x]['data']);byte(sec,0)
   elif kind=='relocation':r=next(r for r in e.relas if r['section']=='.text'and r['offset']<50000 and e.syms[r['symbol']]['name']=='printk');r['addend']+=4
   elif kind=='symbol':s=next(s for s in e.syms if s['type']==2 and s['name']==('ieee80211_setmode'if component=='wlan'else'qdrv_hostlink_msg_cmd'));s['other']=1
   else:s=next(s for s in e.syms if s['type']==2 and s['name']=='ieee80211_param_from_qdrv');byte('.text',s['value']+116)
   try:audit(old,e,component)
   except(AssertionError,ValueError)as ex:rows.append(dict(component=component,case=kind,rejected=True,reason=str(ex)))
   else:rows.append(dict(component=component,case=kind,rejected=False))
 assert len(rows)==11 and all(r['rejected']for r in rows)
 for path,h in pins.items():assert sha(path)==h,'negative input drift'
 (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_ELEVEN_SOURCE25_PARSED_NEGATIVE_DELTA_CASES',hardware_accessed=False,files_modified=False,cases=len(rows),rows=rows);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
