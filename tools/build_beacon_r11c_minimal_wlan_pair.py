"""Compile exactly four R11c WLAN units twice against qualified R10 closure.

Fifteen unmodified WLAN objects and six complete modules retain exact qualified
R10 source lineage. Headers/QDRV sources must match R10. No hardware/firmware.
"""
import argparse,hashlib,json,os,shutil
from pathlib import Path
import build_hgw5g_typed_header_closure as b

CHANGED={'ieee80211','ieee80211_wireless','ieee80211_output','ieee80211_beacon'}
COMPONENTS=['qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--r10-build',type=Path,required=True);p.add_argument('--r10-qualified',type=Path,required=True);p.add_argument('--r9-first',type=Path,required=True);p.add_argument('--r9-second',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 proof=json.loads(a.r10_qualified.read_text());assert proof['status']=='PASS_OFFLINE_R10_COMPLETE_PAIR_CLEANUP_DELIVERY'
 cp=json.loads((a.candidate/'result.json').read_text());assert cp['status']=='SOURCE_ONLY_R11_ALL_APP_READERS_SYNCHRONIZATION_PENDING_FIXTURES_BUILD'and not cp['wire_header_changes']
 assert set(cp['changed_sources'])=={'source/wlan/'+n+'.c'for n in CHANGED}
 for rel,h in cp['changed_sources'].items():assert sha(a.candidate/rel)==h
 # Complete source membership checked in both directions, changes only four.
 for tree in ['source/qdrv','source/wlan','headers']:
  left={str(p.relative_to(a.parent_source/tree)):p for p in(a.parent_source/tree).rglob('*')if p.is_file()}
  right={str(p.relative_to(a.candidate/tree)):p for p in(a.candidate/tree).rglob('*')if p.is_file()}
  assert set(left)==set(right),'source membership '+tree
  for rel,path in left.items():
   if tree=='source/wlan'and Path(rel).stem in CHANGED and Path(rel).suffix=='.c':continue
   assert sha(path)==sha(right[rel]),'unrelated source/header changed '+tree+'/'+rel
 qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers'
 names=json.loads((b.wb.ROOT/'outputs/rea/driver5g-ops-20261022-wlan-baseline-r2/result.json').read_text())['units'];assert len(names)==19 and CHANGED<=set(names)
 pins={}
 for parent in[a.r9_first,a.r9_second,a.r10_build]:
  for path,h in json.loads((parent/'input-pins.json').read_text()).items():assert sha(path)==h,'parent closure drift '+path;pins[path]=h
 paths={Path(__file__),Path(b.__file__),Path(b.wb.__file__),Path(b.qb.context.__file__),a.r10_qualified,a.r10_build/'result.json',a.candidate/'result.json',a.parent_source/'result.json'}
 paths.update(p for tree in[qsrc,wsrc,headers]for p in tree.rglob('*')if p.is_file())
 for lane,parent in [('a',a.r9_first),('b',a.r9_second)]:
  assert json.loads((parent/'result.json').read_text())['source_c_units']==58
  assert sha(parent/'wlan/wlan.ko')==sha(a.r10_build/lane/'wlan/wlan.ko')
  for name in names:paths.update(parent/'wlan'/(name+x)for x in['.o','.d']);paths.add(parent/'wlan'/('.'+name+'.o.cmd'))
  for c in COMPONENTS:paths.add(a.r10_build/lane/c/(c+'.ko'))
 paths.update([a.r9_first/'Module.symvers',a.r9_first/'retained-dependencies.symvers'])
 for path in paths:pins[str(path)]=sha(path)
 canonical={os.path.abspath(path)for path in pins};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
 result={'status':'NO_GO_R11C_INCREMENTAL_WLAN_PAIR','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'modules':[],'changed_source_names':sorted(CHANGED),'new_source_unit_compiles':8,'unchanged_WLAN_units_reused_per_lane':15,'other_exact_R10_modules':6,'headers_QDRV_sources_unchanged':True}
 try:
  rows=[]
  for line in(a.r9_first/'Module.symvers').read_text().splitlines():
   fields=line.split('\t');owner=fields[2].replace('\\','/').rsplit('/',1)[-1]
   if owner not in['wlan','wlan.o','wlan.ko']:rows.append(line)
  dep=a.output/'dependencies.symvers';dep.write_text((a.r9_first/'retained-dependencies.symvers').read_text()+'\n'.join(rows)+'\n')
  for lane,parent in [('a',a.r9_first),('b',a.r9_second)]:
   folder=a.output/lane/'wlan';folder.mkdir(parents=True)
   for name in names:
    if name in CHANGED:
     cmd,_=b.compile_command('wlan',name,folder,qsrc,wsrc,headers);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+name));ds=b.readdeps(folder/(name+'.d'));missing={os.path.abspath(Path(x)if x.startswith('/')else b.qb.context.CONTEXT/x)for x in ds}-canonical;assert not missing,'unpinned dependency '+repr(sorted(missing))
     (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(wsrc/(name+'.c'))+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
    else:
     shutil.copyfile(parent/'wlan'/(name+'.o'),folder/(name+'.o'));shutil.copyfile(parent/'wlan'/(name+'.d'),folder/(name+'.d'));shutil.copyfile(parent/'wlan'/('.'+name+'.o.cmd'),folder/('.'+name+'.o.cmd'))
   objs=[str(folder/(n+'.o'))for n in names];(folder/'wlan.mod').write_text('\n'.join(objs)+'\n');b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/'wlan.o'),*objs],folder,folder/'link-source')
   b.run([str(b.qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(dep),'-o',str(folder/'Module.symvers'),str(folder/'wlan.o')],folder,folder/'modpost');assert not(folder/'modpost.stderr').read_text().strip(),'modpost diagnostics'
   cmd,_=b.compile_command('wlan','wlan.mod',folder,qsrc,wsrc,headers,True);b.run(cmd,b.qb.context.CONTEXT,folder/'compile-metadata');b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(b.qb.context.CONTEXT/'scripts/module.lds'),'-o',str(folder/'wlan.ko'),str(folder/'wlan.o'),str(folder/'wlan.mod.o')],folder,folder/'link-module')
   for c in COMPONENTS:
    target=a.output/lane/c/(c+'.ko')
    if c!='wlan':target.parent.mkdir();shutil.copyfile(a.r10_build/lane/c/(c+'.ko'),target)
    result['modules'].append({'component':c,'lane':lane,'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target)})
  for c in COMPONENTS:assert sha(a.output/'a'/c/(c+'.ko'))==sha(a.output/'b'/c/(c+'.ko')),'reproducibility '+c
  for path,h in pins.items():assert sha(path)==h,'input drift '+path
  result.update(status='PASS_R11C_FOUR_WLAN_UNITS_TWICE_COMPLETE_PAIR_PENDING_DELTA',reproducible=True,input_pins=len(pins),inputs_unchanged=True)
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(not result['status'].startswith('PASS_'))
if __name__=='__main__':raise SystemExit(main())
