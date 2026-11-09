"""Continue a SOURCE23/beacon first compile lane via validated joint closure.

Do not replace historical failed standalone-modpost receipt. Reuse exactly its
58 fresh source objects; compile the second lane58 once, joint compose both.
Only unchanged old source/header dependency bytes are accepted. No hardware.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--first-build',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();first=json.loads((a.first_build/'result.json').read_text());assert first['status']=='NO_GO_TYPED_HEADER_CLOSURE'and len(first['units'])==58 and 'om_ieee80211_beacon_frame_status'in first['error'];a.output.mkdir(parents=True)
 qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers';groups=[('qdrv',b.parse_names(qsrc)),('wlan',json.loads((a.wlan_baseline/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]];assert sum(len(ns)for c,ns in groups)==58
 pins=json.loads((a.first_build/'input-pins.json').read_text());paths=[Path(__file__),Path(b.__file__),a.first_build/'result.json',a.first_build/'input-pins.json',a.candidate/'result.json']
 for c,names in groups:
  for name in names:paths.extend([a.first_build/'a'/c/(name+'.o'),a.first_build/'a'/c/(name+'.d'),a.first_build/'a'/c/('.'+name+'.o.cmd')])
 for path in paths:pins[str(path)]=sha(path)
 for path,h in pins.items():assert sha(path)==h,'firstlane input drift '+path
 canonical={os.path.abspath(path)for path in pins};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');rows=[]
 for c,names in groups:
  folder=a.output/'a'/c;folder.mkdir(parents=True)
  for name in names:
   cmd,source=b.compile_command(c,name,folder,qsrc,wsrc,headers);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+name));deps=b.readdeps(folder/(name+'.d'));assert not {os.path.abspath(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in deps}-canonical,'newdependency'
   (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n');row={'component':c,'name':name,'source_sha256':sha(source),'object_sha256':sha(folder/(name+'.o'))};rows.append(row);print(json.dumps(row),flush=True)
 for path,h in pins.items():assert sha(path)==h,'secondlane drift '+path
 # Composer expects this documented status; no standalone linked module claim.
 (a.output/'result.json').write_text(json.dumps({'status':'NO_GO_TYPED_HEADER_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'units':rows,'source_compiles':58,'error':'STANDALONE_MODPOST_NOT_ATTEMPTED_USE_VALIDATED_JOINT_COMPOSITION','inputs_unchanged':True},indent=2)+'\n')
 for name,build in [('first',a.first_build),('second',a.output)]:
  output=a.output/(name+'-joint');cmd=[sys.executable,str(Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py'),'--source-build',str(build),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(output)];b.run(cmd,b.qb.context.CONTEXT,a.output/(name+'-compose'))
 one=json.loads((a.output/'first-joint/result.json').read_text());two=json.loads((a.output/'second-joint/result.json').read_text());assert one['status']==two['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'first-joint'/c/(c+'.ko'))==sha(a.output/'second-joint'/c/(c+'.ko')),'pair module reproducibility '+c
 result={'status':'PASS_CONSOLIDATED23_BEACON_R12_SOURCE58X2_JOINT_SEVEN_MODULE_PAIR_PENDING_GLOBAL','hardware_accessed':False,'firmware_eligible':False,'new_source_compiles':58,'first_source_compiles_reused':58,'reproducible':True,'first_joint':str(a.output/'first-joint'),'second_joint':str(a.output/'second-joint'),'modules':one['modules'],'limits':'Complete source58x2/joint strongimports only; whole matchedcontrolresidual/ABI/fixtures stillseparate; nohardware.'};(a.output/'pair-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
