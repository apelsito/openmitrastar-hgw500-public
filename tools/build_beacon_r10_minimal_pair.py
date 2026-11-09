"""Compile the one R10 changed unit twice and relink complete QDRV, offline.

Requires an accepted R9 global scope receipt. Every reused object is from its
source-built composition. Other six modules are exact R9 bytes. No firmware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import build_hgw5g_typed_header_closure as b

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd,cwd,log):
 log.with_suffix('.command.json').write_text(json.dumps(cmd,indent=2)+'\n');p=subprocess.run(cmd,cwd=cwd,capture_output=True,timeout=300);log.with_suffix('.stdout').write_bytes(p.stdout);log.with_suffix('.stderr').write_bytes(p.stderr)
 assert not p.returncode,log.name+': '+p.stderr.decode(errors='replace')[-2500:]

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--r9-first',type=Path,required=True);p.add_argument('--r9-second',type=Path,required=True);p.add_argument('--r9-qualified',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 proof=json.loads(a.r9_qualified.read_bytes());assert proof['status']=='PASS_OFFLINE_R9_LIFETIME_CONTROLLED_SEVEN_MODULE_SCOPE'
 cp=json.loads((a.candidate/'result.json').read_bytes());assert cp['added_calls']==2 and not cp['wire_or_header_changes'];qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers';names=b.parse_names(qsrc);assert len(names)==34
 assert sha(qsrc/'qdrv_wlan.c')==cp['candidate_qdrv_source_sha256']=='35c3b912c1d4e0a0fda0db2300627deef11cb7b042ed5fba56e577feb23d6445'
 paths={Path(__file__),Path(b.__file__),a.r9_qualified,a.candidate/'result.json',a.r9_first/'result.json',a.r9_second/'result.json',a.r9_first/'Module.symvers',a.r9_first/'retained-dependencies.symvers'}
 paths.update(x for t in(qsrc,wsrc,headers)for x in t.rglob('*')if x.is_file())
 # Pin actual recorded closure before the changed unit compile.
 for parent in(a.r9_first,a.r9_second):
  for name in names:
   paths.update(parent/'qdrv'/(name+x)for x in('.o','.d'))
   paths.add(parent/'qdrv'/('.'+name+'.o.cmd'))
   for value in (parent/'qdrv'/(name+'.d')).read_text().split(':',1)[1].replace('\\\n',' ').split():
    path=Path(value)if value.startswith('/')else b.qb.context.CONTEXT/value
    if path.is_file():paths.add(path)
  paths.update(x for x in parent.rglob('*.ko'))
 for tree in('include/generated','include/config','arch/arc/include/generated'):paths.update(x for x in(b.qb.context.CONTEXT/tree).rglob('*')if x.is_file())
 paths.update([b.qb.context.CONTEXT/'.config',b.qb.context.CONTEXT/'scripts/mod/modpost',b.qb.context.CONTEXT/'scripts/module.lds',Path(str(b.qb.context.TC)+'gcc'),Path(str(b.qb.context.TC)+'ld')])
 pins={str(x):sha(x)for x in paths};canonical={os.path.abspath(x)for x in pins};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
 result={'status':'NO_GO_R10_MINIMAL_COMPLETE_PAIR','hardware_accessed':False,'firmware_eligible':False,'modules':[],'limits':'ExactlytwoSOURCEcleanupcalls; sourceunit2x/fullQdrvlink2x, residualqualification stillrequired.'}
 try:
  # Other candidate providers resolve against their exact R9 export contracts;
  # omit QDRV rows because they will be regenerated from this candidate.
  external=a.output/'dependencies.symvers';rows=[]
  for line in (a.r9_first/'Module.symvers').read_text().splitlines():
   fields=line.split('\t');owner=fields[2].replace('\\','/').rsplit('/',1)[-1]
   if owner not in('qdrv','qdrv.o','qdrv.ko'):rows.append(line)
  external.write_text((a.r9_first/'retained-dependencies.symvers').read_text()+'\n'.join(rows)+'\n')
  for lane,parent in(('a',a.r9_first),('b',a.r9_second)):
   out=a.output/lane/'qdrv';out.mkdir(parents=True)
   cmd,_=b.compile_command('qdrv','qdrv_wlan',out,qsrc,wsrc,headers);run(cmd,b.qb.context.CONTEXT,out/'compile-qdrv_wlan')
   deps=(out/'qdrv_wlan.d').read_text().split(':',1)[1].replace('\\\n',' ').split();assert not {os.path.abspath(Path(x)if x.startswith('/')else b.qb.context.CONTEXT/x)for x in deps}-canonical,'unpinnedchangedunitdependency'
   for name in names:
    if name!='qdrv_wlan':(out/(name+'.o')).write_bytes((parent/'qdrv'/(name+'.o')).read_bytes())
    if name=='qdrv_wlan':
     (out/('.'+name+'.o.cmd')).write_text('source_'+str(out/(name+'.o'))+' := '+str(qsrc/(name+'.c'))+'\n\ndeps_'+str(out/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n')
    else:
     (out/('.'+name+'.o.cmd')).write_bytes((parent/'qdrv'/('.'+name+'.o.cmd')).read_bytes())
   objs=[str(out/(name+'.o'))for name in names];(out/'qdrv.mod').write_text('\n'.join(objs)+'\n');run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(out/'qdrv.o'),*objs],out,out/'link-source')
   run([str(b.qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-i',str(external),'-o',str(out/'Module.symvers'),str(out/'qdrv.o')],out,out/'modpost')
   cmd,_=b.compile_command('qdrv','qdrv.mod',out,qsrc,wsrc,headers,True);run(cmd,b.qb.context.CONTEXT,out/'compile-metadata');run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(b.qb.context.CONTEXT/'scripts/module.lds'),'-o',str(out/'qdrv.ko'),str(out/'qdrv.o'),str(out/'qdrv.mod.o')],out,out/'link-module')
   for c in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
    if c!='qdrv':target=a.output/lane/c;target.mkdir();(target/(c+'.ko')).write_bytes((parent/c/(c+'.ko')).read_bytes())
    target=a.output/lane/c/(c+'.ko');result['modules'].append({'lane':lane,'component':c,'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target)})
  for c in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):assert sha(a.output/'a'/c/(c+'.ko'))==sha(a.output/'b'/c/(c+'.ko'))
  for path,h in pins.items():assert sha(path)==h,'inputdrift '+path
  result.update(status='PASS_R10_ONE_SOURCE_UNIT_TWICE_COMPLETE_PAIR_PENDING_DELTA',reproducible=True,input_pins=len(pins),all_inputs_unchanged=True,unchanged_R9_QDRV_objects_reused=33,unchanged_R9_modules_exact=6)
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(not result['status'].startswith('PASS_'))
if __name__=='__main__':raise SystemExit(main())
