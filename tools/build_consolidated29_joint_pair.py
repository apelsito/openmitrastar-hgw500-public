"""Pinned source29 complete58×2 ARC compile and joint seven-module closure.

Uses actual syntax-parent dependency context and existing strict dedup composer.
No standalone-modpost deadend, baseline object reuse, firmware or hardware.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--syntax-build',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();sp=json.loads((a.syntax_build/'result.json').read_text());assert sp['status']=='PASS_ACTUAL_TYPED_HEADER_SYNTAX_UNITS';a.output.mkdir(parents=True);qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers';groups=[('qdrv',b.parse_names(qsrc)),('wlan',json.loads((a.wlan_baseline/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]];assert sum(len(names)for c,names in groups)==58
 pins=json.loads((a.syntax_build/'input-pins.json').read_text());paths=[Path(__file__),Path(b.__file__),Path(b.qb.__file__),Path(b.wb.__file__),a.candidate/'result.json',a.syntax_build/'result.json',a.syntax_build/'input-pins.json']
 for parent in[a.wlan_baseline,a.qdrv_baseline]:
  for path,h in json.loads((parent/'input-pins.json').read_text()).items():assert sha(path)==h;pins[path]=h
 for path in paths:pins[str(path)]=sha(path)
 for path,h in pins.items():assert sha(path)==h,'precompilepin '+path
 canonical={os.path.abspath(path)for path in pins};rows=[]
 for lane in ['a','b']:
  wave=a.output/lane;wave.mkdir();(wave/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');wr=[]
  for c,names in groups:
   folder=wave/'a'/c;folder.mkdir(parents=True)
   for name in names:
    cmd,source=b.compile_command(c,name,folder,qsrc,wsrc,headers);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+name));ds=b.readdeps(folder/(name+'.d'));assert not {os.path.abspath(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical,'unpinneddeps '+name
    (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n');row={'lane':lane,'component':c,'name':name,'source_sha256':sha(source),'object_sha256':sha(folder/(name+'.o'))};wr.append(row);rows.append(row);print(json.dumps(row),flush=True)
  for path,h in pins.items():assert sha(path)==h,'postcompilepin '+path
  # Composer-compatible source-objectreceipt; no standalone link attempted.
  (wave/'result.json').write_text(json.dumps({'status':'NO_GO_TYPED_HEADER_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'units':wr,'source_compiles':58,'no_baseline_objects_reused':True,'error':'SOURCE_OBJECT_WAVE_JOINT_LINK_REQUIRED','inputs_unchanged':True},indent=2)+'\n')
  cmd=[sys.executable,str(Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py'),'--source-build',str(wave),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(a.output/(lane+'-joint'))];b.run(cmd,b.qb.context.CONTEXT,a.output/(lane+'-joint-run'))
 one=json.loads((a.output/'a-joint/result.json').read_text());two=json.loads((a.output/'b-joint/result.json').read_text());assert one['status']==two['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'a-joint'/c/(c+'.ko'))==sha(a.output/'b-joint'/c/(c+'.ko')),'modulereproducibility '+c
 result={'status':'PASS_CONSOLIDATED29_SOURCE58X2_JOINT_SEVEN_MODULES_PENDING_GLOBAL','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'source_compiles':116,'units':rows,'modules':one['modules'],'reproducible':True,'pins':len(pins),'limits':'Fullsource/jointclosureonly; matchedglobalABI/recordsemantics stillseparate; nohardware.'};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
