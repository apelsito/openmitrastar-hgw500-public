"""FourchangedSOURCE32Cunits×2+54exactparent30objects/jointsevenmodules.

Private scannerABIappendverified, public/hostheadersexactbeforeobjectreuse.
NewAPI-onlyscanheaderprefixremoval exact andsizeof scannerallocationbound.
"""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--first',type=Path,required=True);p.add_argument('--second',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--syntax',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();assert json.loads(a.qualification.read_text())['status']=='PASS_OFFLINE_CONSOLIDATED30_R2_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT';ab=json.loads(a.abi.read_text());assert ab['status']=='PASS_ARC_CONSOLIDATED32_PUBLIC_HOST_PREFIX_AND_PRIVATE_SCANNER_APPEND';assert json.loads((a.syntax/'result.json').read_text())['status']=='PASS_ACTUAL_CONSOLIDATED32_FOUR_TYPED_UNITS_INC_PIN_CLOSURE'
 old={str(p.relative_to(a.parent_source/'source')).replace('\\','/'):sha(p)for p in(a.parent_source/'source').rglob('*')if p.is_file()};new={str(p.relative_to(a.candidate/'source')).replace('\\','/'):sha(p)for p in(a.candidate/'source').rglob('*')if p.is_file()};added=set(new)-set(old);assert added=={'wlan/openmitrastar_chanset_kernel.inc','wlan/openmitrastar_chanset_recovered.c','wlan/openmitrastar_chanset_recovered.h','wlan/openmitrastar_chanset_tables.h'}and not set(old)-set(new);changed={k for k in old if old[k]!=new[k]};assert changed=={'wlan/ieee80211_scan.c','wlan/ieee80211_scan_ap.c','wlan/ieee80211_proto.c','wlan/ieee80211_wireless.c'}
 for p in(a.parent_source/'headers').rglob('*'):
  if p.is_file():assert sha(p)==sha(a.candidate/p.relative_to(a.parent_source))
 scanheader=a.candidate/'headers/net80211/ieee80211_scan.h';original=b.qb.ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_scan.h';oldheader=original.read_text();newheader=scanheader.read_text();start=newheader.index('\n/* Recovered OEM461 scanner state');end=newheader.index('\n#endif /* _NET80211_IEEE80211_SCAN_H_ */',start);assert newheader[:start].rstrip()+newheader[end:]==oldheader
 pins={}
 for directory in[a.first,a.second]:
  r=json.loads((directory/'result.json').read_text());assert r['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
  for path,h in json.loads((directory/'input-pins.json').read_text()).items():assert sha(path)==h;pins[path]=h
 for directory in[a.syntax,a.abi.parent]:
  for path,h in json.loads((directory/'input-pins.json').read_text()).items():assert sha(path)==h;pins[path]=h
 for root in['source','headers']:
  for p in(a.candidate/root).rglob('*'):
   if p.is_file():pins[str(p)]=sha(p)
 for p in[Path(__file__),Path(b.__file__),a.candidate/'result.json',a.qualification,a.abi,scanheader,original]:pins[str(p)]=sha(p)
 for p,h in pins.items():assert sha(p)==h
 canonical={b.key(path)for path in pins};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');q,w,h=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';groups=[('qdrv',b.parse_names(q)),('wlan',json.loads((a.wlan_baseline/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]];rows=[]
 for lane,parent in [('a',a.first),('b',a.second)]:
  wave=a.output/lane;wave.mkdir();wr=[]
  for c,names in groups:
   folder=wave/'a'/c;folder.mkdir(parents=True)
   for n in names:
    rel=('qdrv'if c=='qdrv'else'wlan')+'/'+n+'.c';src=a.candidate/'source'/rel;fresh=rel in changed
    if fresh:
     cmd,_=b.compile_command(c,n,folder,q,w,h);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n));ds=b.readdeps(folder/(n+'.d'));assert not {b.key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical,'unpinned32'+n;(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(src)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
    else:
     for ext in['.o','.d']:shutil.copyfile(parent/c/(n+ext),folder/(n+ext))
     shutil.copyfile(parent/c/('.'+n+'.o.cmd'),folder/('.'+n+'.o.cmd'));command=next(Path(p)for p in pins if p.endswith('/'+c+'/compile-'+n+'.command.json'));shutil.copyfile(command,folder/('compile-'+n+'.command.json'))
    row={'lane':lane,'component':c,'name':n,'source_sha256':sha(src),'object_sha256':sha(folder/(n+'.o')),'fresh':fresh};rows.append(row);wr.append(row);print(json.dumps(row),flush=True)
  for p,digest in pins.items():assert sha(p)==digest
  (wave/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(wave/'result.json').write_text(json.dumps({'status':'NO_GO_TYPED_HEADER_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'units':wr,'no_baseline_objects_reused':True,'error':'FOUR_CHANGED_SOURCE_UNITS_WITH_54_QUALIFIED_PARENT30_OBJECTS_JOINT_REQUIRED'},indent=2)+'\n')
  cmd=[sys.executable,str(Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py'),'--source-build',str(wave),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(a.output/(lane+'-joint'))];b.run(cmd,b.qb.context.CONTEXT,a.output/(lane+'-compose'))
 a1=json.loads((a.output/'a-joint/result.json').read_text());b1=json.loads((a.output/'b-joint/result.json').read_text());assert a1['status']==b1['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'a-joint'/c/(c+'.ko'))==sha(a.output/'b-joint'/c/(c+'.ko'))
 result={'status':'PASS_CONSOLIDATED32_FOUR_CHANGED_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'units':rows,'new_compiled_units':8,'reused_parent30_objects':108,'reproducible':True,'modules':a1['modules'],'pins':len(pins),'limits':'Public/hostABIunchanged/privateappendownallocation; sourcepairedlinkonly, globaloperation/lifetimephysicalgatepending.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
