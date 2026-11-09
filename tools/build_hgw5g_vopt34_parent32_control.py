"""Complete58 same-VOPT-header control using verified unchanged units +5 fresh.

Reuse only source-identical candidate objects with unchanged every actual dep.
Control semantics remain SOURCE32. No old ABI modules/baselineobjects reused.
"""
import argparse,hashlib,json,os,shutil
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(p):return os.path.abspath(os.fspath(p))
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--selected-source',type=Path,required=True);p.add_argument('--selected-pair',type=Path,required=True);p.add_argument('--wlan-baseline-build',type=Path,required=True);p.add_argument('--qdrv-baseline-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();pair=json.loads((a.selected_pair/'result.json').read_text());assert pair['status'].startswith('PASS_ALL_R9_TYPED_MODULES'),pair['status'];spins=json.loads((a.selected_pair/'input-pins.json').read_text())
 for path,h in spins.items():assert sha(path)==h
 q,w,headers=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';qnames=b.parse_names(q);wnames=json.loads((a.wlan_baseline_build/'result.json').read_text())['units'];units=[('qdrv',n)for n in qnames]+[('wlan',n)for n in wnames]+list(b.PROVIDERS.items());assert len(units)==58;protected={Path(__file__),Path(b.__file__),a.candidate/'result.json',a.selected_pair/'result.json',a.selected_pair/'input-pins.json',a.qdrv_baseline_build/'dependencies.symvers',a.wlan_baseline_build/'dependencies.symvers'};protected.update(Path(p)for p in spins)
 for root in(q,w,headers):protected.update(x for x in root.rglob('*')if x.is_file()and x.suffix in('.c','.h','.inc'))
 eligible=[];rows={(r['component'],r['name']):r for r in pair['units']if r['lane']=='a'}
 for c,n in units:
  src=(q if c=='qdrv'else w)/(n+'.c');selected=a.selected_source/'source'/('qdrv'if c=='qdrv'else'wlan')/(n+'.c');folder=a.selected_pair/'a'/c;obj=folder/(n+'.o');dep=folder/(n+'.d');protected.update([obj,dep]);can=sha(src)==sha(selected)
  if can:
   assert sha(obj)==rows[c,n]['object_sha256'];
   for d in b.readdeps(dep):
    path=Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d
    try:mapped=a.candidate/path.relative_to(a.selected_source)
    except ValueError:mapped=path
    if mapped.is_file()and sha(mapped)!=sha(path):can=False
  if can:eligible.append((c,n))
 pins={str(x):sha(x)for x in protected};canon={key(x)for x in protected};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='NO_GO_VOPT34_PARENT32_SAME_HEADER_CONTROL',hardware_accessed=False,firmware_eligible=False,units=[],modules=[],limits='Complete58controlledobjects, unchangedsource/actualdepsreusedverified; changedfiveunitsfresh. Nophysicalclaim.')
 try:
  for c,n in units:
   folder=a.output/'a'/c;folder.mkdir(parents=True,exist_ok=True);src=(q if c=='qdrv'else w)/(n+'.c');fresh=(c,n)not in eligible
   if fresh:
    cmd,_=b.compile_command(c,n,folder,q,w,headers);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n))
   else:
    old=a.selected_pair/'a'/c;shutil.copyfile(old/(n+'.o'),folder/(n+'.o'));shutil.copyfile(old/(n+'.d'),folder/(n+'.d'))
   deps=b.readdeps(folder/(n+'.d'));assert not({key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in deps}-canon);(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(src)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n');row=dict(component=c,name=n,source_sha256=sha(src),object_sha256=sha(folder/(n+'.o')),fresh=fresh);result['units'].append(row);print(json.dumps(row),flush=True)
  for c,names in [('qdrv',qnames),('wlan',wnames),*[(c,[n])for c,n in b.PROVIDERS.items()]]:
   folder=a.output/'a'/c;objects=[str(folder/(n+'.o'))for n in names];(folder/(c+'.mod')).write_text('\n'.join(objects)+'\n');b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/(c+'.o')),*objects],folder,folder/'link-relocatable');dep=a.qdrv_baseline_build/'dependencies.symvers'if c=='qdrv'else a.wlan_baseline_build/'dependencies.symvers';b.run([str(b.qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(dep),'-o',str(folder/'Module.symvers'),str(folder/(c+'.o'))],folder,folder/'modpost');cmd,_=b.compile_command(c,c+'.mod',folder,q,w,headers,True);b.run(cmd,b.qb.context.CONTEXT,folder/'compile-metadata');b.run([str(b.qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(b.qb.context.CONTEXT/'scripts/module.lds'),'-o',str(folder/(c+'.ko')),str(folder/(c+'.o')),str(folder/(c+'.mod.o'))],folder,folder/'link-module');result['modules'].append(dict(component=c,path=str(folder/(c+'.ko')),sha256=sha(folder/(c+'.ko')),bytes=(folder/(c+'.ko')).stat().st_size))
  for path,h in pins.items():assert sha(path)==h
  result.update(status='PASS_COMPLETE58_PARENT32_SAME_VOPT34_HEADER_CONTROL',fresh_compiles=sum(r['fresh']for r in result['units']),reused_verified=sum(not r['fresh']for r in result['units']),inputs_unchanged=True)
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='units'},indent=2));return int(not result['status'].startswith('PASS'))
if __name__=='__main__':raise SystemExit(main())
