"""Select short pseudocode windows from immutable OEM evidence, nofullJSONdump."""
import argparse,json,re
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('path',type=Path);p.add_argument('--pattern',default='bf4|478|memset|__kmalloc|kzalloc');a=p.parse_args();data=json.loads(a.path.read_text());found=[]
 def walk(x,key=''):
  if isinstance(x,dict):
   for k,v in x.items():walk(v,k)
  elif isinstance(x,list):
   for v in x:walk(v,key)
  elif isinstance(x,str)and key in('text','pseudocode','code','content'):
   lines=x.splitlines()
   for i,s in enumerate(lines):
    if re.search(a.pattern,s):found.append(dict(field=key,line=i,context='\n'.join(lines[max(0,i-3):i+4])))
 walk(data);print(json.dumps(found[:30],indent=2))
if __name__=='__main__':main()
