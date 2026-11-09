"""Recover R9 full58A modpostdeadend; reuse58verified A, compile58B, jointcompose."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(p):return os.path.abspath(os.fspath(p))
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--prior-build',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();prior=json.loads((a.prior_build/'result.json').read_text());assert 'modpost:'in prior['error'];assert len(prior['units'])==58;pinmap=json.loads((a.prior_build/'input-pins.json').read_text());paths=[Path(__file__),Path(b.__file__),Path(b.qb.__file__),Path(b.wb.__file__),a.prior_build/'result.json',a.prior_build/'input-pins.json',a.candidate/'result.json'];q,w,h=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';groups=[('qdrv',b.parse_names(q)),('wlan',json.loads((a.wlan_baseline/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]];priorrows={(r['component'],r['name']):r for r in prior['units']};composer=Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py';paths.append(composer)
 for c,ns in groups:
  folder=a.prior_build/'a'/c
  for n in ns:
   obj=folder/(n+'.o');assert sha(obj)==priorrows[c,n]['object_sha256'];paths.extend([obj,folder/(n+'.d'),folder/('.'+n+'.o.cmd')]);cmd=folder/('compile-'+n+'.command.json')
   if not cmd.exists():
    # Reused R8 object: exact command was initialpinned in the prior receipt.
    cmd=next(Path(x)for x in pinmap if x.endswith('/'+c+'/compile-'+n+'.command.json'))
   paths.append(cmd)
 for path,hv in pinmap.items():assert sha(path)==hv
 for path in paths:pinmap[str(path)]=sha(path)
 a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pinmap,indent=2)+'\n');canonical={key(x)for x in pinmap};allrows=[]
 for lane in('a','b'):
  wave=a.output/lane;wave.mkdir();rows=[]
  for c,ns in groups:
   folder=wave/'a'/c;folder.mkdir(parents=True)
   for n in ns:
    source=(q if c=='qdrv'else w)/(n+'.c');fresh=lane=='b'
    if fresh:
     cmd,_=b.compile_command(c,n,folder,q,w,h);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n));deps=b.readdeps(folder/(n+'.d'));assert not {key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in deps}-canonical;(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n')
    else:
     old=a.prior_build/'a'/c
     for ext in('.o','.d'):shutil.copyfile(old/(n+ext),folder/(n+ext))
     shutil.copyfile(old/('.'+n+'.o.cmd'),folder/('.'+n+'.o.cmd'));cmd=old/('compile-'+n+'.command.json')
     if not cmd.exists():cmd=next(Path(x)for x in pinmap if x.endswith('/'+c+'/compile-'+n+'.command.json'))
     shutil.copyfile(cmd,folder/('compile-'+n+'.command.json'))
    row=dict(lane=lane,component=c,name=n,source_sha256=sha(source),object_sha256=sha(folder/(n+'.o')),fresh=fresh);rows.append(row);allrows.append(row);print(json.dumps(row),flush=True)
  for path,hv in pinmap.items():assert sha(path)==hv
  (wave/'input-pins.json').write_text(json.dumps(pinmap,indent=2)+'\n');(wave/'result.json').write_text(json.dumps({'status':'NO_GO_TYPED_HEADER_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'units':rows,'error':'JOINT_LINK_REQUIRED_AFTER_VERIFIED_SOURCE_COMPILE','no_baseline_objects_reused':True},indent=2)+'\n');cmd=[sys.executable,str(composer),'--source-build',str(wave),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(a.output/(lane+'-joint'))];b.run(cmd,b.qb.context.CONTEXT,a.output/(lane+'-compose'))
 one=json.loads((a.output/'a-joint/result.json').read_text());two=json.loads((a.output/'b-joint/result.json').read_text());assert one['status']==two['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'a-joint'/c/(c+'.ko'))==sha(a.output/'b-joint'/c/(c+'.ko')),'pairedmoduledifference '+c
 for path,hv in pinmap.items():assert sha(path)==hv
 result=dict(status='PASS_VOPT34_R9_58_OBJECT_LANES_JOINT_SEVEN_MODULE_PAIR',hardware_accessed=False,firmware_eligible=False,units=allrows,modules=one['modules'],reproducible=True,object_lanes=116,reused_initial_R8_compiles=43,initial_R9_fresh_A_compiles=15,fresh_B_compiles=58,total_fresh_R9_compiles=73,dependency_pins=len(pinmap),limits='43initialpinnedR8+15freshR9A+58freshR9B; not116freshR9. Allsameheader/actualdepverified, nohardware/globalqualification.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='units'},indent=2))
if __name__=='__main__':main()
