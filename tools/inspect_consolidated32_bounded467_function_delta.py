"""Read-only list exact symbol-body deltas; never mask semantics."""
import argparse,json
from pathlib import Path
from qualify_f370_qdrv_module import Elf
from collections import Counter
def syms(e):
 cnt=Counter();out={}
 for s in e.syms:
  if s['type']!=2 or not s['size']:continue
  k=(s['name'],e.symsection(s),cnt[(s['name'],e.symsection(s))]);cnt[(s['name'],e.symsection(s))]+=1;out[k]=s
 return out
def body(e,s):return e.byname[e.symsection(s)]['data'][s['value']:s['value']+s['size']]
def main():
 p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);a=p.parse_args();old,new=Elf(a.old),Elf(a.new);os,ns=syms(old),syms(new)
 for k,s in os.items():
  if k not in ns:print(json.dumps(dict(missing=k)));continue
  x,y=body(old,s),body(new,ns[k])
  if x!=y:
   delta=[(i,x[i],y[i])for i in range(min(len(x),len(y)))if x[i]!=y[i]];print(json.dumps(dict(name=k,old_size=len(x),new_size=len(y),delta_count=len(delta),delta=delta[:20])))
 for k in set(ns)-set(os):print(json.dumps(dict(added=k,size=ns[k]['size'])))
if __name__=='__main__':main()
