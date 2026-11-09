"""Print boundedselecteddossier function/call facets, notfullone-linejson."""
import argparse,json,re
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('path',type=Path);p.add_argument('--code',action='store_true');p.add_argument('--filter',default='');a=p.parse_args();d=json.loads(a.path.read_text());found=[]
 def walk(x):
  if isinstance(x,dict):
   if isinstance(x.get('pseudocode'),str)and x.get('procedure'):found.append(x)
   for v in x.values():walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(d)
 if not found:print(json.dumps({'error':d.get('error',d.get('data',{}).get('error'))}));return
 f=max(found,key=lambda x:len(x['pseudocode']));proc=f['procedure'];r={'procedure':{'address':proc.get('address'),'name':proc.get('name'),'body':proc.get('body')},'callers':[{'address':x.get('address'),'name':x.get('name')}for x in f.get('callers',[])],'callees':[{'address':x.get('address'),'name':x.get('name')}for x in f.get('callees',[])],'limitations':f.get('limitations')};print(json.dumps(r,indent=2))
 if a.code:
  lines=f['pseudocode'].splitlines()
  if a.filter:
   seen=set()
   for i,line in enumerate(lines):
    if re.search(a.filter,line):
     for j in range(max(0,i-3),min(len(lines),i+5)):
      if j not in seen:print(str(j)+': '+lines[j]);seen.add(j)
  else:print('\n'.join(lines[:180]))
if __name__=='__main__':main()
