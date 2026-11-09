"""Resume55verifiedSOURCE29 units without accepting lateunqualifiedCCMPbytes.

New pinned context includesallretainedprovider dependencies; recompilesmissing3
units before joint link; thenfreshsecond58. Originalpartialoutputsimmutable.
"""
import argparse,hashlib,json,os,shutil,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b
from recover_hgw5g_driver_ops import Elf
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--partial',type=Path,required=True);p.add_argument('--provider-context',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers';groups=[('qdrv',b.parse_names(qsrc)),('wlan',json.loads((a.wlan_baseline/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]];missing={'wlan_ccmp','wlan_tkip','wlan_xauth'};pins=json.loads((a.partial/'a/input-pins.json').read_text());context=json.loads((a.provider_context/'input-pins.json').read_text())
 for path,h in context.items():assert sha(path)==h,'retainedcontextdrift '+path;pins[path]=h
 for path in [Path(__file__),a.partial/'partial-stop.json',a.candidate/'result.json']:pins[str(path)]=sha(path)
 for c,names in groups:
  if c in missing:continue
  for name in names:
   folder=a.partial/'a/a'/c;assert(folder/(name+'.o')).exists()
   for ext in ['.o','.d']:pins[str(folder/(name+ext))]=sha(folder/(name+ext))
   for d in b.readdeps(folder/(name+'.d')):p=Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d;pins[str(p)]=sha(p)
 for path,h in pins.items():assert sha(path)==h
 canonical={os.path.abspath(path)for path in pins};allrows=[]
 for lane in ['a','b']:
  wave=a.output/lane;wave.mkdir();(wave/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');rows=[]
  for c,names in groups:
   folder=wave/'a'/c;folder.mkdir(parents=True)
   for name in names:
    src=(qsrc if c=='qdrv'else wsrc)/(name+'.c');reuse=lane=='a'and c not in missing
    if reuse:
     parent=a.partial/'a/a'/c
     for ext in ['.o','.d']:shutil.copyfile(parent/(name+ext),folder/(name+ext))
     for f in [parent/('.'+name+'.o.cmd'),parent/('compile-'+name+'.command.json')]:shutil.copyfile(f,folder/f.name)
    else:
     cmd,_=b.compile_command(c,name,folder,qsrc,wsrc,headers);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+name));ds=b.readdeps(folder/(name+'.d'));delta={os.path.abspath(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical;assert not delta,'unpinneddeps '+repr(delta);(folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(src)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
    row={'lane':lane,'component':c,'name':name,'source_sha256':sha(src),'object_sha256':sha(folder/(name+'.o')),'reused_verified_partial_source_compile':reuse};rows.append(row);allrows.append(row);print(json.dumps(row),flush=True)
  for path,h in pins.items():assert sha(path)==h
  (wave/'result.json').write_text(json.dumps({'status':'NO_GO_TYPED_HEADER_CLOSURE','units':rows,'source_compiles':58,'hardware_accessed':False,'firmware_eligible':False,'no_baseline_objects_reused':True,'error':'SOURCE_OBJECT_WAVE_JOINT_LINK_REQUIRED'},indent=2)+'\n')
  cmd=[sys.executable,str(Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py'),'--source-build',str(wave),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(a.output/(lane+'-joint'))];b.run(cmd,b.qb.context.CONTEXT,a.output/(lane+'-compose'))
 one=json.loads((a.output/'a-joint/result.json').read_text());two=json.loads((a.output/'b-joint/result.json').read_text());assert one['status']==two['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'a-joint'/c/(c+'.ko'))==sha(a.output/'b-joint'/c/(c+'.ko'))
 result={'status':'PASS_CONSOLIDATED29_116_SOURCE_COMPILES_JOINT_MODULE_PAIR_PENDING_GLOBAL','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'source_units_firstwave_verified_reused':55,'source_units_firstwave_recompiled':3,'source_units_secondwave_fresh':58,'total_verified_source_compiles':116,'units':allrows,'modules':one['modules'],'reproducible':True,'pin_count':len(pins),'limits':'First55freshcompilesfrompartialretained; lateCCMPobjrejected/recompiledunderpre-pinnedfullprovidercontext. Global/moduleABI/recordsemanticstillseparate.'};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
