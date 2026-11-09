"""Resume complete candidate source objects and compose exports jointly.

Uses only immutable source-built candidate objects, never baseline objects.
All seven objects are passed together to modpost so new paired exports resolve.
Existing source build/evidence are retained and rehashed; one explicit lane.
"""
import argparse, hashlib, json, shutil
from pathlib import Path
import build_hgw5g_typed_header_closure as b
from recover_hgw5g_driver_ops import Elf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-build',required=True,type=Path);p.add_argument('--candidate',required=True,type=Path);p.add_argument('--lane',default='a',choices=['a','b']);p.add_argument('--qdrv-baseline-build',required=True,type=Path);p.add_argument('--wlan-baseline-build',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 assert not a.output.exists();source_proof=json.loads((a.source_build/'result.json').read_text());assert source_proof['status'] in ('NO_GO_TYPED_HEADER_CLOSURE','PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA')
 qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers';qnames=b.parse_names(qsrc);wnames=json.loads((a.wlan_baseline_build/'result.json').read_text())['units'];groups=[('qdrv',qnames),('wlan',wnames),*[(c,[n])for c,n in b.PROVIDERS.items()]]
 pins=json.loads((a.source_build/'input-pins.json').read_text());paths={Path(__file__),Path(b.__file__),a.source_build/'result.json',a.source_build/'input-pins.json'}
 for path,h in pins.items():assert sha(path)==h,'source-build input drift '+path
 for c,names in groups:
  old=a.source_build/a.lane/c
  for n in names:paths.update([old/(n+'.o'),old/(n+'.d'),old/('.'+n+'.o.cmd'),old/('compile-'+n+'.command.json')])
 pinmap={str(p):sha(p)for p in paths};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pinmap,indent=2)+'\n')
 result={'status':'NO_GO_JOINT_TYPED_MODULE_COMPOSITION','hardware_accessed':False,'firmware_eligible':False,'source_build':str(a.source_build),'source_lane':a.lane,'baseline_objects_used':False,'source_c_units':58,'modules':[]}
 try:
  linked=[]
  for c,names in groups:
   folder=a.output/c;folder.mkdir();old=a.source_build/a.lane/c
   for n in names:
    for suffix in ('.o','.d'):shutil.copyfile(old/(n+suffix),folder/(n+suffix))
    shutil.copyfile(old/('.'+n+'.o.cmd'),folder/('.'+n+'.o.cmd'))
   objects=[str(folder/(n+'.o'))for n in names];(folder/(c+'.mod')).write_text('\n'.join(objects)+'\n')
   b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/(c+'.o')),*objects],folder,folder/'link-relocatable');linked.append(str(folder/(c+'.o')))
  deps=a.output/'retained-dependencies.symvers';deps.write_text((a.qdrv_baseline_build/'dependencies.symvers').read_text()+(a.wlan_baseline_build/'dependencies.symvers').read_text())
  b.run([str(b.qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(deps),'-o',str(a.output/'Module.symvers'),*linked],a.output,a.output/'joint-modpost')
  modules={}
  for c,names in groups:
   folder=a.output/c;cmd,_=b.compile_command(c,c+'.mod',folder,qsrc,wsrc,headers,True);b.run(cmd,b.qb.context.CONTEXT,folder/'compile-metadata')
   path=folder/(c+'.ko');b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(b.qb.context.CONTEXT/'scripts/module.lds'),'-o',str(path),str(folder/(c+'.o')),str(folder/(c+'.mod.o'))],folder,folder/'link-module')
   elf=Elf(path);modules[c]=elf;result['modules'].append({'component':c,'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)})
  exports={}
  for c,e in modules.items():
   for s in e.syms:
    if s['name'].startswith('__ksymtab_'):exports[s['name'][10:]]=c
  closure=[]
  for c,e in modules.items():
   imports=[s['name']for s in e.syms if s['section']==0 and s['name']]
   for name in imports:
    if name.startswith('om_') or name.startswith('omcgq_'):assert name in exports,'unresolved paired export '+name
   closure.append({'component':c,'internal_imports':{n:exports[n]for n in imports if n in exports}})
  for path,h in pins.items():assert sha(path)==h,'source-build pin changed '+path
  for path,h in pinmap.items():assert sha(path)==h,'candidate object changed '+path
  result.update(status='PASS_JOINT_TYPED_MODULE_COMPOSITION',inputs_unchanged=True,closure=closure,complete_modules=7)
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(not result['status'].startswith('PASS_'))
if __name__=='__main__':raise SystemExit(main())
