"""Every58MDID35headeruser freshcompiledtwice/jointmodules, nohardware.

VAPsizeof+4 precludesparentobjectreuse. Exactparent32/syntax/ABI dependency
contextandnewsourceheaders pinnedbeforecompile, including scanner.inc.
"""
import argparse,hashlib,json,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-pins',type=Path,required=True);p.add_argument('--syntax',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();assert json.loads((a.syntax/'result.json').read_text())['status']=='PASS_ACTUAL_TYPED_HEADER_SYNTAX_UNITS';assert json.loads((a.abi/'result.json').read_text())['status']=='PASS_ARC_MDID35_ALL_OLD_VAP_PREFIX_AND_QDRV_VAP_SHIFT4';a.output.mkdir(parents=True);q,w,h=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';groups=[('qdrv',b.parse_names(q)),('wlan',json.loads((a.wlan_baseline/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]];pins={}
 for pathmap in[a.parent_pins,a.syntax/'input-pins.json',a.abi/'actual/input-pins.json']:
  for path,digest in json.loads(pathmap.read_text()).items():assert sha(path)==digest;pins[path]=digest
 for root in['source','headers']:
  for path in(a.candidate/root).rglob('*'):
   if path.is_file():pins[str(path)]=sha(path)
 for path in[Path(__file__),Path(b.__file__),a.candidate/'result.json',a.abi/'result.json']:pins[str(path)]=sha(path)
 canonical={b.key(path)for path in pins};rows=[]
 for lane in['a','b']:
  wave=a.output/lane;wave.mkdir();(wave/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');wr=[]
  for c,names in groups:
   folder=wave/'a'/c;folder.mkdir(parents=True)
   for n in names:
    cmd,source=b.compile_command(c,n,folder,q,w,h);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n));ds=b.readdeps(folder/(n+'.d'));assert not {b.key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical,'unpinneddeps'+n;(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n');r={'lane':lane,'component':c,'name':n,'source_sha256':sha(source),'object_sha256':sha(folder/(n+'.o'))};wr.append(r);rows.append(r);print(json.dumps(r),flush=True)
  for path,digest in pins.items():assert sha(path)==digest
  (wave/'result.json').write_text(json.dumps({'status':'NO_GO_TYPED_HEADER_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'units':wr,'no_baseline_objects_reused':True,'error':'FULL_FRESH_VAP_HEADER_WAVE_JOINT_REQUIRED'},indent=2)+'\n');cmd=[sys.executable,str(Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py'),'--source-build',str(wave),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(a.output/(lane+'-joint'))];b.run(cmd,b.qb.context.CONTEXT,a.output/(lane+'-compose'))
 ar=json.loads((a.output/'a-joint/result.json').read_text());br=json.loads((a.output/'b-joint/result.json').read_text());assert ar['status']==br['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'a-joint'/c/(c+'.ko'))==sha(a.output/'b-joint'/c/(c+'.ko'))
 r={'status':'PASS_MDID35_ALL58_HEADER_USERS_FRESH_TWO_WAVES_JOINT_MODULES_PENDING_GLOBAL','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'source_units_fresh':116,'units':rows,'modules':ar['modules'],'reproducible':True,'pins':len(pins),'limits':'FullrecompileVAPdelta4+jointclosure only; matchedparentheadercontrol/residual/semantic/physicalgates separate.'};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
