"""Expose exact named function, symbol, data and padding deltas before audit freezing."""
import argparse,json,hashlib
from collections import Counter
from pathlib import Path
from qualify_f370_qdrv_module import Elf
def symbols(e):
 c=Counter();out={}
 for s in e.syms:
  base=(s['name'],e.symsection(s),s['type']);key=(*base,c[base]);c[base]+=1;out[key]=s
 return out
def body(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]
def main():
 p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);old,new=Elf(a.old),Elf(a.new);os,ns=symbols(old),symbols(new);func=[];data=[]
 for k,s in os.items():
  if k not in ns:continue
  if s['type']not in(1,2)or not s['size']or old.symsection(s)not in old.byname:continue
  t=ns[k];x,y=body(old,s),body(new,t)
  if x!=y:
   row={'key':k,'old_value':s['value'],'new_value':t['value'],'old_size':s['size'],'new_size':t['size'],'old_sha256':hashlib.sha256(x).hexdigest(),'new_sha256':hashlib.sha256(y).hexdigest()}
   if s['type']==2:
    row['byte_deltas']=[(p,x[p],y[p])for p in range(min(len(x),len(y)))if x[p]!=y[p]];func.append(row)
   elif s['type']==1:data.append(row)
 def gaps(e):
  rows=[]
  for sec,v in e.byname.items():
   if not v['flags']&4:continue
   fs=sorted([s for s in e.syms if s['type']==2 and s['size']and e.symsection(s)==sec],key=lambda s:s['value']);p=0;nops=0;non=0
   for s in fs:
    x=v['data'][p:s['value']]
    while x.startswith(bytes.fromhex('e078')):nops+=2;x=x[2:]
    non+=len(x);p=max(p,s['value']+s['size'])
   rows.append({'section':sec,'nops':nops,'anonymous':non+len(v['data'])-p})
  return rows
 added=[k for k in ns if k not in os];removed=[k for k in os if k not in ns];r={'status':'INSPECTION_ONLY_NOT_QUALIFICATION','functions':func,'data':data,'added':added,'removed':removed,'old_padding':gaps(old),'new_padding':gaps(new)};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'functions':[(x['key'][0],x['old_size'],x['new_size'],len(x['byte_deltas']))for x in func],'added':added,'removed':removed,'old_padding':r['old_padding'],'new_padding':r['new_padding']},indent=2))
if __name__=='__main__':main()
