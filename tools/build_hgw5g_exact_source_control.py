"""Same-header SOURCE23 control from exact candidate closure plus four rebuilds.

Every source/header hash and actual source-object receipt is rechecked. Reuse
only 54 unchanged-source units under identical headers/flags, compile exact
four changed units in fresh output; compose separately with joint modpost.
This is a control artifact, never a firmware or an independent paired build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import build_hgw5g_typed_header_closure as b

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--control',type=Path,required=True);p.add_argument('--source-build',type=Path,required=True);p.add_argument('--wlan-baseline-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);proof=json.loads((a.source_build/'result.json').read_text());assert proof['status']=='NO_GO_TYPED_HEADER_CLOSURE'and len(proof['units'])==58;assert 'om_ieee80211_coc_quiesce' in proof.get('error','');pins=json.loads((a.source_build/'input-pins.json').read_text());candidate_sources=a.candidate/'source';control_sources=a.control/'source'
 for path,h in pins.items():assert sha(path)==h,'original build input drift '+path
 controls={x.relative_to(control_sources).as_posix():sha(x)for x in control_sources.rglob('*')if x.is_file()and x.suffix in('.c','.h')};candidates={x.relative_to(candidate_sources).as_posix():sha(x)for x in candidate_sources.rglob('*')if x.is_file()and x.suffix in('.c','.h')};assert set(controls)==set(candidates);changed={k for k in controls if controls[k]!=candidates[k]};expected={'qdrv/qdrv_wlan.c','wlan/ieee80211.c','wlan/ieee80211_node.c','wlan/ieee80211_wireless.c'};assert changed==expected,changed
 for rel,h in controls.items():pins[str(control_sources/rel)]=h
 hc={x.relative_to(a.control/'headers').as_posix():sha(x)for x in(a.control/'headers').rglob('*')if x.is_file()};hh={x.relative_to(a.candidate/'headers').as_posix():sha(x)for x in(a.candidate/'headers').rglob('*')if x.is_file()};assert hc==hh
 for rel,h in hc.items():pins[str(a.control/'headers'/rel)]=h
 pins[str(Path(__file__))]=sha(__file__);pins[str(a.control/'result.json')]=sha(a.control/'result.json');pins[str(a.source_build/'result.json')]=sha(a.source_build/'result.json');pins[str(a.source_build/'input-pins.json')]=sha(a.source_build/'input-pins.json');results=[];qsrc=a.control/'source/qdrv';wsrc=a.control/'source/wlan';headers=a.control/'headers'
 # Candidatecommand flags map only source/includes/outputpaths; sourceidentity
 # and exactheaderhash are the admission for54reusedobjects, not a broadmask.
 for row in proof['units']:
  component,name=row['component'],row['name'];old=a.source_build/'a'/component;folder=a.output/'a'/component;folder.mkdir(parents=True,exist_ok=True);source=qsrc/(name+'.c')if component=='qdrv'else wsrc/(name+'.c');cand=(a.candidate/'source/qdrv'if component=='qdrv'else a.candidate/'source/wlan')/(name+'.c');assert sha(cand)==row['source_sha256'];assert sha(old/(name+'.o'))==row['object_sha256'];pins[str(old/(name+'.o'))]=row['object_sha256'];pins[str(old/('compile-'+name+'.command.json'))]=sha(old/('compile-'+name+'.command.json'));cmd,_=b.compile_command(component,name,folder,qsrc,wsrc,headers)
  if sha(source)==sha(cand):
   for suffix in('.o','.d'):shutil.copyfile(old/(name+suffix),folder/(name+suffix))
   shutil.copyfile(old/('.'+name+'.o.cmd'),folder/('.'+name+'.o.cmd'));(folder/('compile-'+name+'.command.json')).write_bytes((old/('compile-'+name+'.command.json')).read_bytes());reused=True
  else:
   b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+name));deps=b.readdeps(folder/(name+'.d'));canonical={b.key(Path(x))for x in pins}
   missing={b.key(Path(x)if x.startswith('/')else b.qb.context.CONTEXT/x)for x in deps}-canonical;assert not missing,'unpinned control dependencies '+str(sorted(missing));(folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n');reused=False
  r=dict(lane='a',component=component,name=name,source_sha256=sha(source),object_sha256=sha(folder/(name+'.o')),reused_exact_source_header_object=reused);results.append(r);print(json.dumps(r),flush=True)
 for path,h in pins.items():assert sha(path)==h,'post control input drift '+path
 (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_SAME_HEADER_EXACT_SOURCE_CONTROL_OBJECT_CLOSURE',hardware_accessed=False,firmware_eligible=False,candidate=str(a.control),source_units=58,units=results,recompiled_units=4,reused_exact_source_header_units=54,header_identical=True,inputs_unchanged=True,limits='Controlonly;54unchangedSOURCE25objectsreusedaftersource/headeridentity; fouractualSOURCE23unitsfreshcompiled; jointmodpostseparate. Notsecondindependentcandidatebuild.')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return 0

if __name__=='__main__':raise SystemExit(main())
