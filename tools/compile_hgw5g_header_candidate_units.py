"""Pinned ARC compile gate for selected typed-header source units, new output only."""
import argparse, hashlib, json, os
from pathlib import Path
import subprocess
import build_f370_qdrv_module as q
import build_wlan_txmaxmpdu_alias_module as w
from qualify_f370_qdrv_module import Elf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--wlan-unit',action='append',default=[]);p.add_argument('--qdrv-unit',action='append',default=[]);a=p.parse_args()
 assert not a.output.exists();a.output.mkdir(parents=True);candidate=a.candidate.resolve();headers=candidate/'headers';units=[]
 paths={Path(__file__),Path(q.__file__),Path(w.__file__),q.context.CONTEXT/'.config',q.context.CONTEXT/'Module.symvers',Path(str(q.context.TC)+'gcc')}
 paths.update(x for x in (candidate/'source').rglob('*') if x.is_file());paths.update(x for x in headers.rglob('*') if x.is_file())
 # Source and exact header dependencies are pinned before compilation.
 templates=[]
 for component,names in (('qdrv',a.qdrv_unit),('wlan',a.wlan_unit)):
  for name in names:
   source=candidate/'source'/component/(name+'.c');folder=a.output/component;folder.mkdir(exist_ok=True)
   if component=='qdrv':cmd,template=q.command(name,source.parent,folder)
   else:cmd=w.command(name,folder,source);template=w.OLD/('.'+name+'.o.cmd')
   paths.add(template)
   for row in template.read_text().splitlines()[1:]:
    token=row.strip().removesuffix('\\').strip()
    if not token or token.startswith(('$','deps_','source_')) or ':' in token or ' ' in token:continue
    token=token.replace('/home/user/mitrastar-linux-5.10.260',str(q.context.KERNEL))
    path=Path(token) if token.startswith('/') else q.context.CONTEXT/token
    if path.is_file():paths.add(path)
   # Candidate overlays always precede retained GPL headers.
   cmd[1:1]=['-I'+str(headers),'-I'+str(candidate/'source/wlan'),'-I'+str(candidate/'source/qdrv'),'-I'+str(q.context.OLD/'compat/include')]
   units.append((component,name,source,folder,cmd))
 for tree in ('include/generated','include/config','arch/arc/include/generated'):
  paths.update(x for x in (q.context.CONTEXT/tree).rglob('*') if x.is_file())
 pins={str(p):sha(p) for p in paths};canonical={os.path.abspath(p) for p in pins};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
 result={'status':'NO_GO_ARC_SOURCE_COMPILE','hardware_accessed':False,'firmware_eligible':False,'module_built':False,'units':[]}
 try:
  for component,name,source,folder,cmd in units:
   (folder/(name+'.command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
   r=subprocess.run(cmd,cwd=q.context.CONTEXT,capture_output=True,timeout=180);(folder/(name+'.stdout')).write_bytes(r.stdout);(folder/(name+'.stderr')).write_bytes(r.stderr)
   assert r.returncode==0,name+': '+r.stderr.decode(errors='replace')[-3000:]
   deps=(folder/(name+'.d')).read_text().split(':',1)[1].replace('\\\n',' ').split()
   missing={os.path.abspath(Path(d) if d.startswith('/') else q.context.CONTEXT/d) for d in deps}-canonical
   assert not missing,'Unpinned deps '+str(sorted(missing))
   obj=folder/(name+'.o');elf=Elf(obj);result['units'].append({'component':component,'name':name,'source_sha256':sha(source),'object_sha256':sha(obj),'object_bytes':obj.stat().st_size,'machine':93,'functions':sum(s['type']==2 for s in elf.syms)})
   print(json.dumps(result['units'][-1]),flush=True)
  for p,h in pins.items():assert sha(p)==h,'input drift '+p
  result.update(status='PASS_ARC_TYPED_HEADER_SOURCE_UNITS',input_pins=len(pins),inputs_unchanged=True)
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(result['status']!='PASS_ARC_TYPED_HEADER_SOURCE_UNITS')
if __name__=='__main__':raise SystemExit(main())
