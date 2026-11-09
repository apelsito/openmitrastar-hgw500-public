"""Paired r3/control modules reusing only exact fresh MDID35 header-wave objects."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--seed',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--seed-source',type=Path,required=True);p.add_argument('--variant',choices=['r3','control32'],required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 seed=json.loads((a.seed/'result.json').read_text());assert seed['status']=='PASS_MDID35_ALL58_HEADER_USERS_FRESH_TWO_WAVES_JOINT_MODULES_PENDING_GLOBAL'
 for path in(a.seed_source/'headers').rglob('*'):
  if path.is_file():assert sha(path)==sha(a.candidate/path.relative_to(a.seed_source)),('headerdiff',str(path))
 old={str(x.relative_to(a.seed_source/'source')).replace('\\','/'):sha(x)for x in(a.seed_source/'source').rglob('*')if x.is_file()};new={str(x.relative_to(a.candidate/'source')).replace('\\','/'):sha(x)for x in(a.candidate/'source').rglob('*')if x.is_file()};assert set(old)==set(new)
 changed={k for k in old if old[k]!=new[k]};expected={'wlan/ieee80211_output.c'}if a.variant=='r3'else{'wlan/ieee80211_output.c','wlan/ieee80211_beacon.c','wlan/ieee80211_beacon_desc.c','wlan/ieee80211_wireless.c'};assert changed==expected,changed
 pins=json.loads((a.seed/'input-pins.json').read_text())
 for path,d in pins.items():assert sha(path)==d
 for tree in['source','headers']:
  for x in(a.candidate/tree).rglob('*'):
   if x.is_file():pins[str(x)]=sha(x)
 for x in[Path(__file__),Path(b.__file__),a.seed/'result.json',a.candidate/'result.json']:pins[str(x)]=sha(x)
 q,w,h=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';groups=[('qdrv',b.parse_names(q)),('wlan',json.loads((a.wlan_baseline/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]]
 for lane in['a','b']:
  for c,names in groups:
   for n in names:
    folder=a.seed/lane/'a'/c
    for suffix in['.o','.d']:pins[str(folder/(n+suffix))]=sha(folder/(n+suffix))
    for x in[folder/('.'+n+'.o.cmd'),folder/('compile-'+n+'.command.json')]:pins[str(x)]=sha(x)
 a.output.mkdir(parents=True);canonical={b.key(path)for path in pins};rows=[]
 for lane in['a','b']:
  wave=a.output/lane;wave.mkdir();wr=[]
  for c,names in groups:
   folder=wave/'a'/c;folder.mkdir(parents=True)
   for n in names:
    src=(q if c=='qdrv'else w)/(n+'.c');rel=('qdrv'if c=='qdrv'else'wlan')+'/'+n+'.c';fresh=rel in changed;oldfolder=a.seed/lane/'a'/c
    if fresh:
     cmd,_=b.compile_command(c,n,folder,q,w,h);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n));ds=b.readdeps(folder/(n+'.d'));assert not {b.key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical,'unpinned'+n;(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(src)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
    else:
     assert sha(src)==sha((a.seed_source/'source'/rel));assert next(x for x in seed['units']if x['lane']==lane and x['component']==c and x['name']==n)['object_sha256']==sha(oldfolder/(n+'.o'))
     for suffix in['.o','.d']:shutil.copyfile(oldfolder/(n+suffix),folder/(n+suffix))
     for name in['.'+n+'.o.cmd','compile-'+n+'.command.json']:shutil.copyfile(oldfolder/name,folder/name)
    r={'lane':lane,'component':c,'name':n,'source_sha256':sha(src),'object_sha256':sha(folder/(n+'.o')),'fresh':fresh};wr.append(r);rows.append(r)
    if fresh:print(json.dumps(r),flush=True)
  for path,d in pins.items():assert sha(path)==d
  (wave/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(wave/'result.json').write_text(json.dumps({'status':'NO_GO_TYPED_HEADER_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'units':wr,'no_baseline_objects_reused':True,'error':'MATCHED_MDID35_HEADERS_FRESH_SEED_SOURCE_EXACT_OBJECTS_JOINT_REQUIRED'},indent=2)+'\n')
  cmd=[sys.executable,str(Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py'),'--source-build',str(wave),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(a.output/(lane+'-joint'))];b.run(cmd,b.qb.context.CONTEXT,a.output/(lane+'-compose'))
 ar=json.loads((a.output/'a-joint/result.json').read_text());br=json.loads((a.output/'b-joint/result.json').read_text());assert ar['status']==br['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'a-joint'/c/(c+'.ko'))==sha(a.output/'b-joint'/c/(c+'.ko'))
 r={'status':'PASS_MDID35_MATCHED_HEADER_'+a.variant.upper()+'_PAIRED_MODULES_PENDING_GLOBAL','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'seed':str(a.seed),'units':rows,'fresh_compiles':sum(x['fresh']for x in rows),'same_header_exact_source_objects_reused':sum(not x['fresh']for x in rows),'modules':ar['modules'],'pins':len(pins),'reproducible':True,'limits':'All58seedusersfreshcompiled×2 withnewVAPextent; reuseonlyexactsameC/headers. Variantglobalresidual/sourcefixture/physicalgatesremainseparate.'};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
