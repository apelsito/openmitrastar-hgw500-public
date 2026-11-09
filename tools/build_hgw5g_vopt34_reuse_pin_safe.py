"""R9 closure reuses only completed R8 objects whose initial pins cover all deps.

Explicitly records counts. A inc-pin failure makes that object ineligible. LaneB
recompiles every unit; new inputs including .inc are pinned before any compilation.
"""
import argparse,hashlib,json,os,shutil
from pathlib import Path
import build_hgw5g_typed_header_closure as b

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(p):return os.path.abspath(os.fspath(p))

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--prior-candidate',type=Path,required=True);p.add_argument('--prior-build',type=Path,required=True);p.add_argument('--wlan-baseline-build',type=Path,required=True);p.add_argument('--qdrv-baseline-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();oldresult=json.loads((a.prior_build/'result.json').read_text());assert not oldresult['status'].startswith('PASS'),'this gate is for actual terminal pinerror recovery';assert 'unpinneddependencies' in oldresult['error'];oldpins=json.loads((a.prior_build/'input-pins.json').read_text());oldcanon={key(x):h for x,h in oldpins.items()};
 for path,h in oldpins.items():assert sha(path)==h,'oldinputdrift '+path
 qsrc,wsrc,headers=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';qnames=b.parse_names(qsrc);wnames=json.loads((a.wlan_baseline_build/'result.json').read_text())['units'];units=[('qdrv',n)for n in qnames]+[('wlan',n)for n in wnames]+[(c,n)for c,n in b.PROVIDERS.items()];assert len(units)==58;protected={Path(__file__),Path(b.__file__),Path(b.qb.__file__),Path(b.wb.__file__),Path(b.qb.context.__file__),a.candidate/'result.json',a.prior_build/'result.json',a.prior_build/'input-pins.json',a.qdrv_baseline_build/'dependencies.symvers',a.wlan_baseline_build/'dependencies.symvers',b.qb.context.CONTEXT/'scripts/mod/modpost',b.qb.context.CONTEXT/'scripts/module.lds'};protected.update(Path(x)for x in oldpins)
 for root in(qsrc,wsrc,headers):protected.update(x for x in root.rglob('*')if x.is_file()and x.suffix in('.c','.h','.inc'))
 plans={};eligible=[];rejected=[]
 prior_rows={(r['component'],r['name']):r for r in oldresult['units'] if r['lane']=='a'}
 for c,n in units:
  folder=a.prior_build/'a'/c;obj=folder/(n+'.o');dep=folder/(n+'.d');src=qsrc/(n+'.c')if c=='qdrv'else wsrc/(n+'.c');oldsrc=a.prior_candidate/'source'/('qdrv'if c=='qdrv'else'wlan')/(n+'.c');can=(c,n)in prior_rows and obj.is_file()and dep.is_file()and sha(src)==sha(oldsrc)
  missing=[]
  if can:
   assert sha(obj)==prior_rows[c,n]['object_sha256'];deps=b.readdeps(dep)
   for value in deps:
    path=Path(value)if value.startswith('/')else b.qb.context.CONTEXT/value
    if key(path)not in oldcanon or sha(path)!=oldcanon.get(key(path)):missing.append(str(path))
    try:newpath=a.candidate/path.relative_to(a.prior_candidate)
    except ValueError:newpath=path
    if newpath.is_file()and sha(newpath)!=sha(path):missing.append('newcontextdiff '+str(path))
   can=not missing
  if can:eligible.append((c,n));protected.update([obj,dep,folder/('compile-'+n+'.command.json')])
  else:rejected.append({'component':c,'name':n,'reason':'notcompletedoractualdepsnotinitialpinned','missing':missing})
 pins={str(x):sha(x)for x in protected};canon={key(x)for x in protected};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='NO_GO_R9_PIN_SAFE_REUSE_CLOSURE',hardware_accessed=False,firmware_eligible=False,units=[],modules=[],reused_verified=len(eligible),fresh_expected=116-len(eligible),rejected_reuse=rejected,limits='Reusedcompletedcandidateobjectscoveredinitialpins; explicitlynot116freshcompilations. Fullmoduleglobaldelta/physicalgatesseparate.')
 try:
  for lane in('a','b'):
   for c,n in units:
    folder=a.output/lane/c;folder.mkdir(parents=True,exist_ok=True);source=qsrc/(n+'.c')if c=='qdrv'else wsrc/(n+'.c')
    if lane=='a'and(c,n)in eligible:
     old=a.prior_build/'a'/c;shutil.copyfile(old/(n+'.o'),folder/(n+'.o'));shutil.copyfile(old/(n+'.d'),folder/(n+'.d'));fresh=False
    else:
     cmd,_=b.compile_command(c,n,folder,qsrc,wsrc,headers);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n));fresh=True
    deps=b.readdeps(folder/(n+'.d'));missing={key(Path(x)if x.startswith('/')else b.qb.context.CONTEXT/x)for x in deps}-canon;assert not missing,'unpinnedactualdeps '+repr(missing);(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n');row=dict(lane=lane,component=c,name=n,source_sha256=sha(source),object_sha256=sha(folder/(n+'.o')),fresh=fresh);result['units'].append(row);print(json.dumps(row),flush=True)
   for component,names in [('qdrv',qnames),('wlan',wnames),*[(c,[n])for c,n in b.PROVIDERS.items()]]:
    folder=a.output/lane/component;objects=[str(folder/(n+'.o'))for n in names];(folder/(component+'.mod')).write_text('\n'.join(objects)+'\n');b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/(component+'.o')),*objects],folder,folder/'link-relocatable');depsfile=a.qdrv_baseline_build/'dependencies.symvers'if component=='qdrv'else a.wlan_baseline_build/'dependencies.symvers';b.run([str(b.qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(depsfile),'-o',str(folder/'Module.symvers'),str(folder/(component+'.o'))],folder,folder/'modpost');cmd,_=b.compile_command(component,component+'.mod',folder,qsrc,wsrc,headers,True);b.run(cmd,b.qb.context.CONTEXT,folder/'compile-metadata');b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(b.qb.context.CONTEXT/'scripts/module.lds'),'-o',str(folder/(component+'.ko')),str(folder/(component+'.o')),str(folder/(component+'.mod.o'))],folder,folder/'link-module');module=folder/(component+'.ko');result['modules'].append(dict(lane=lane,component=component,path=str(module),sha256=sha(module),bytes=module.stat().st_size))
  for path,h in pins.items():assert sha(path)==h,'pindrift '+path
  comparisons={c:sha(a.output/'a'/c/(c+'.ko'))==sha(a.output/'b'/c/(c+'.ko'))for c in('qdrv','wlan',*b.PROVIDERS)}
  result.update(status='PASS_ALL_R9_TYPED_MODULES_PENDING_DELTA'if all(comparisons.values())else'NO_GO_R9_SOURCE_IDENTITY_NONREPRODUCIBILITY',reproducible_modules=comparisons,inputs_unchanged=True,fresh_compiles=sum(r['fresh']for r in result['units']),reused_verified=sum(not r['fresh']for r in result['units']))
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in('units','rejected_reuse')},indent=2));return int(not result['status'].startswith('PASS'))
if __name__=='__main__':raise SystemExit(main())
