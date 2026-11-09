"""Compile six changed same-header25 control C units, reuse52 exact29 units.

No new candidate build or firmware. Every reused source/header/object is bound
to the completed first29 source wave and original commands/dependencies.
"""
import argparse,hashlib,json,shutil
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--control',type=Path,required=True);p.add_argument('--source-build',type=Path,required=True);p.add_argument('--precompiled-control',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();proof=json.loads((a.source_build/'result.json').read_text());assert proof['status']=='NO_GO_TYPED_HEADER_CLOSURE'and len(proof['units'])==58 and proof['error']=='SOURCE_OBJECT_WAVE_JOINT_LINK_REQUIRED';a.output.mkdir(parents=True);pins=json.loads((a.source_build/'input-pins.json').read_text())
 if a.precompiled_control:
  pc=json.loads((a.precompiled_control/'result.json').read_text());assert pc['status']=='PASS_ACTUAL_TYPED_HEADER_SYNTAX_UNITS'and len(pc['units'])==6
  for path,h in json.loads((a.precompiled_control/'input-pins.json').read_text()).items():assert sha(path)==h;pins[path]=h
 def members(tree):return{str(p.relative_to(tree)):sha(p)for p in tree.rglob('*')if p.is_file()and p.suffix in ['.c','.h']}
 old,new=members(a.control/'source'),members(a.candidate/'source');assert set(old)==set(new);expected={'qdrv/qdrv_wlan.c','wlan/ieee80211.c','wlan/ieee80211_wireless.c','wlan/ieee80211_output.c','wlan/ieee80211_beacon.c','wlan/ieee80211_beacon_desc.c'};changed={k.replace('\\','/')for k in old if old[k]!=new[k]};assert changed==expected,changed;assert members(a.control/'headers')==members(a.candidate/'headers')
 for root in[a.control/'source',a.control/'headers']:
  for path in root.rglob('*'):
   if path.is_file():pins[str(path)]=sha(path)
 for path in[Path(__file__),a.control/'result.json',a.source_build/'result.json',a.source_build/'input-pins.json']:pins[str(path)]=sha(path)
 for path,h in pins.items():assert sha(path)==h,'inputdrift '+path
 qsrc=a.control/'source/qdrv';wsrc=a.control/'source/wlan';headers=a.control/'headers';rows=[]
 for row in proof['units']:
  c,name=row['component'],row['name'];src=(qsrc if c=='qdrv'else wsrc)/(name+'.c');cand=(a.candidate/'source/qdrv'if c=='qdrv'else a.candidate/'source/wlan')/(name+'.c');parent=a.source_build/'a'/c;folder=a.output/'a'/c;folder.mkdir(parents=True,exist_ok=True);assert sha(cand)==row['source_sha256']and sha(parent/(name+'.o'))==row['object_sha256']
  reused=sha(src)==sha(cand)
  if reused:
   for ext in ['.o','.d']:shutil.copyfile(parent/(name+ext),folder/(name+ext))
   shutil.copyfile(parent/('.'+name+'.o.cmd'),folder/('.'+name+'.o.cmd'));shutil.copyfile(parent/('compile-'+name+'.command.json'),folder/('compile-'+name+'.command.json'))
  elif a.precompiled_control:
   unit=next(r for r in pc['units']if r['component']==c and r['name']==name);assert unit['source_sha256']==sha(src);pre=a.precompiled_control/'a'/c;assert unit['object_sha256']==sha(pre/(name+'.o'))
   for ext in ['.o','.d']:shutil.copyfile(pre/(name+ext),folder/(name+ext));pins[str(pre/(name+ext))]=sha(pre/(name+ext))
   for f in [pre/('.'+name+'.o.cmd'),pre/('compile-'+name+'.command.json')]:shutil.copyfile(f,folder/f.name);pins[str(f)]=sha(f)
  else:
   cmd,_=b.compile_command(c,name,folder,qsrc,wsrc,headers);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+name));ds=b.readdeps(folder/(name+'.d'));assert not {b.key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-{b.key(Path(x))for x in pins},'unpinnedcontrol';(folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(src)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
  pins[str(parent/(name+'.o'))]=sha(parent/(name+'.o'));rows.append({'component':c,'name':name,'source_sha256':sha(src),'object_sha256':sha(folder/(name+'.o')),'reused_exact_source_header_object':reused})
 for path,h in pins.items():assert sha(path)==h,'postdrift '+path
 assert sum(not x['reused_exact_source_header_object']for x in rows)==6
 (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result={'status':'PASS_SAME_HEADER_EXACT_SOURCE_CONTROL_OBJECT_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'units':rows,'source_units':58,'recompiled_units':6,'reused_exact_source_header_units':52,'header_identical':True,'limits':'SOURCE25sameheadercontrol only; notcandidatepairedcompileorfirmware.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
