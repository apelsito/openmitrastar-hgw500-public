"""Ten parsed tampercases for actual bounded467WLAN and APprovider auditors."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from qualify_f370_qdrv_module import Elf
from audit_hgw5g_weather478_modules import audit

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);rows=[];pins={str(Path(__file__)):sha(__file__),str(Path(__file__).with_name('audit_hgw5g_weather478_modules.py')):sha(Path(__file__).with_name('audit_hgw5g_weather478_modules.py'))}
 for c in('qdrv','wlan','wlan_scan_ap'):
  op=a.parent/c/(c+'.ko');np=a.candidate/c/(c+'.ko');old,new=Elf(op),Elf(np);pins[str(op)]=sha(op);pins[str(np)]=sha(np);audit(old,copy.deepcopy(new),c)
  kinds=('function','anonymous','data','relocation','symbol','diagnostic')if c=='wlan'else(('function','anonymous','data','relocation','symbol','diagnostic')if c=='qdrv'else('function','data','relocation','symbol'))
  for kind in kinds:
   e=copy.deepcopy(new)
   def byte(sec,p):z=bytearray(e.byname[sec]['data']);z[p]^=1;e.byname[sec]['data']=bytes(z)
   name='ieee80211_setmode'if c=='wlan'else('qdrv_wlan_stats'if c=='qdrv'else'ap_start')
   if kind=='function':s=next(s for s in e.syms if s['name']==name and s['type']==2);byte(e.symsection(s),s['value'])
   elif kind=='anonymous':byte('.text',250)
   elif kind=='data':sec=next(sec for sec in('.data.once','.rodata')if sec in e.byname and e.byname[sec]['data']);byte(sec,0)
   elif kind=='relocation':r=next(r for r in e.relas if r['section']=='.text'and e.syms[r['symbol']]['name']=='printk');r['addend']+=4
   elif kind=='symbol':s=next(s for s in e.syms if s['name']==name and s['type']==2);s['other']=1
   else:s=next(s for s in e.syms if s['name']==('qdrv_wlan_exit'if c=='qdrv'else'ieee80211_param_from_qdrv')and s['type']==2);byte('.text',s['value']+116)
   try:audit(old,e,c)
   except(AssertionError,ValueError)as ex:rows.append(dict(component=c,case=kind,rejected=True,reason=str(ex)))
   else:rows.append(dict(component=c,case=kind,rejected=False))
 assert len(rows)==16 and all(r['rejected']for r in rows)
 assert all(sha(p)==h for p,h in pins.items());(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_SIXTEEN_WEATHER478_PARSED_NEGATIVE_DELTA_CASES',hardware_accessed=False,files_modified=False,cases=16,rows=rows);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
