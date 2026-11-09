"""Compile only revised Coex26 input twice over its exact paired source closure.

Headers and57otherCunits must match the pairedr2closure exactly. Preserve all
old receipts; reuse eachlane'sobjects, independentlycompileinputineachlane.
Report2new+6retainedSource26changedunits and108qualifiedCoC25unchangedunits.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from build_hgw5g_typed_header_closure import compile_command,run,readdeps,key
import build_f370_qdrv_module as qb

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--parent-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();proof=json.loads((a.parent_build/'result.json').read_text());assert proof['status']=='PASS_COEX26_FOUR_UNITS_PAIRED_EXACT_PARENT_CLOSURE'and proof['reproducible'];pins=json.loads((a.parent_build/'input-pins.json').read_text());
 for path,h in pins.items():assert sha(path)==h
 changed=[]
 for folder in('headers','source'):
  for path in(a.parent_source/folder).rglob('*'):
   if not path.is_file()or path.suffix not in('.c','.h'):continue
   rel=path.relative_to(a.parent_source);new=a.candidate/rel;pins[str(new)]=sha(new)
   if sha(path)!=sha(new):changed.append(rel.as_posix())
 assert changed==['source/wlan/ieee80211_input.c'],changed;pins[str(Path(__file__))]=sha(__file__);pins[str(a.parent_build/'result.json')]=sha(a.parent_build/'result.json');pins[str(a.parent_build/'input-pins.json')]=sha(a.parent_build/'input-pins.json');pins[str(a.candidate/'result.json')]=sha(a.candidate/'result.json');a.output.mkdir(parents=True);units=[];q=a.candidate/'source/qdrv';w=a.candidate/'source/wlan';h=a.candidate/'headers'
 for row in proof['units']:
  lane,c,n=row['lane'],row['component'],row['name'];old=a.parent_build/lane/c;folder=a.output/lane/c;folder.mkdir(parents=True,exist_ok=True)
  for suffix in('.o','.d'):pins[str(old/(n+suffix))]=sha(old/(n+suffix))
  pins[str(old/('.'+n+'.o.cmd'))]=sha(old/('.'+n+'.o.cmd'));pins[str(old/('compile-'+n+'.command.json'))]=sha(old/('compile-'+n+'.command.json'))
  if c=='wlan'and n=='ieee80211_input':
   cmd,source=compile_command(c,n,folder,q,w,h);run(cmd,qb.context.CONTEXT,folder/('compile-'+n));deps=readdeps(folder/(n+'.d'));canonical={key(p)for p in pins};missing={key(Path(p)if p.startswith('/')else qb.context.CONTEXT/p)for p in deps}-canonical;assert not missing,'unpinned'+str(sorted(missing));(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n');fresh=True
  else:
   for suffix in('.o','.d'):shutil.copyfile(old/(n+suffix),folder/(n+suffix))
   shutil.copyfile(old/('.'+n+'.o.cmd'),folder/('.'+n+'.o.cmd'));shutil.copyfile(old/('compile-'+n+'.command.json'),folder/('compile-'+n+'.command.json'));fresh=False
  r=dict(row);r.update(source_sha256=sha((q if c=='qdrv'else w)/(n+'.c')),object_sha256=sha(folder/(n+'.o')),fresh=fresh);units.append(r);print(json.dumps(r),flush=True)
 assert len(units)==116 and all(next(x['object_sha256']for x in units if x['lane']=='a'and x['component']==r['component']and x['name']==r['name'])==r['object_sha256']for r in units if r['lane']=='b')
 assert all(sha(p)==h for p,h in pins.items());(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_COEX26_INPUT_REVISION_PAIRED_SOURCE_CLOSURE',hardware_accessed=False,firmware_eligible=False,candidate=str(a.candidate),units=units,new_input_compiles=2,retained_source26_changed_compiles=6,qualified_parent_whole_units_reused=108,reproducible=True,limits='Onlyinputr3fresh; sixr2changedunitsretainpairedcompilation;108CoC25wholeunitsretainedsource/ABI/headerlineadmitted; jointmodpost/globaldelta separate');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
