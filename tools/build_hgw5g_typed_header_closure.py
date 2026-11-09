"""Generic offline ARC QDRV/net80211 typed-header closure builder.

Explicit source directories and first-priority header overlay. Rebuild every
34QDRV/19WLAN unit plus five scan/crypto/auth providers, two lanes by default.
No binary patching, hardware, config, packaging, runtime or firmware access.
Only actual pre-existing dependency/command/source files are hashed; no kernel
tree crawl. Syntax-only mode compiles selected real units and no modules.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

import build_f370_qdrv_module as qb
import build_wlan_txmaxmpdu_alias_module as wb
from recover_hgw5g_driver_ops import Elf

PROVIDERS={'wlan_scan_ap':'ieee80211_scan_ap','wlan_scan_sta':'ieee80211_scan_sta','wlan_ccmp':'ieee80211_crypto_ccmp','wlan_tkip':'ieee80211_crypto_tkip','wlan_xauth':'ieee80211_xauth'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(p):return os.path.abspath(os.fspath(p))
def readdeps(p):return p.read_text().split(':',1)[1].replace('\\\n',' ').split()
def run(cmd,cwd,log):
 log.with_suffix('.command.json').write_text(json.dumps(cmd,indent=2)+'\n');p=subprocess.run(cmd,cwd=cwd,capture_output=True,timeout=300);log.with_suffix('.stdout').write_bytes(p.stdout);log.with_suffix('.stderr').write_bytes(p.stderr)
 if p.returncode:raise RuntimeError(log.name+': '+p.stderr.decode(errors='replace')[-3000:])
def parse_names(qsrc):return [n[:-2]for n in(qsrc/'Makefile').read_text().split('qdrv-objs :=',1)[1].split('obj-m',1)[0].replace('\\',' ').split()if n.endswith('.o')]

def compile_command(component,name,folder,qsrc,wsrc,headers,metadata=False):
 source=qsrc/(name+'.c')if component=='qdrv'else wsrc/(name+'.c')
 cmd=qb.command(name,qsrc,folder,metadata)[0]if component=='qdrv'else wb.command(name,folder,source)
 if component!='qdrv'and metadata:
  template=wb.OLD/('.'+name+'.o.cmd');cmd=shlex.split(template.read_text().splitlines()[0].split(' := ',1)[1]);mapped=[]
  for arg in cmd:
   arg=arg.replace('/home/user/mitrastar-linux-5.10.260',str(qb.context.KERNEL))
   if arg.startswith('-Wp,-MMD,'):arg='-Wp,-MMD,'+str(folder/(name+'.d'))
   if arg in('-I./arch/arc/include/generated','-I./include','-I./arch/arc/include/generated/uapi','-I./include/generated/uapi'):arg='-I'+str(qb.context.CONTEXT/arg[4:])
   mapped.append(arg)
  cmd=mapped;cmd[cmd.index('-o')+1]=str(folder/(name+'.o'));cmd[-1]=str(folder/(name+'.c'))
 # Overlay ahead of ALL compiler includes; OEMincludes stay fallback only.
 inserts=['-I'+str(headers),'-I'+str(qsrc.parent),'-I'+str(qsrc),'-I'+str(wsrc)]
 cmd[1:1]=inserts
 if not metadata and component!='qdrv':
  # Relative ../qdrv includes come from wsrc and matching candidate qsrc.
  cmd[-1]=str(source)
 return cmd,source

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--qdrv-source',type=Path);p.add_argument('--wlan-source',type=Path);p.add_argument('--headers',type=Path);p.add_argument('--wlan-baseline-build',type=Path,required=True);p.add_argument('--qdrv-baseline-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--syntax-only',action='store_true');p.add_argument('--syntax-unit',action='append',default=[]);p.add_argument('--lanes',type=int,default=2,choices=[1,2]);p.add_argument('--jobs',type=int,default=2,choices=[1,2]);a=p.parse_args()
 qsrc=a.qdrv_source or a.candidate/'source/qdrv';wsrc=a.wlan_source or a.candidate/'source/wlan';headers=a.headers or a.candidate/'headers'
 assert qsrc.is_dir()and wsrc.is_dir()and headers.is_dir();assert not a.output.exists()
 qnames=parse_names(qsrc);wp=json.loads((a.wlan_baseline_build/'result.json').read_text());wnames=wp['units'];assert len(qnames)==34 and len(wnames)==19
 proof=json.loads((a.candidate/'result.json').read_text())
 units=[('qdrv',n)for n in qnames]+[('wlan',n)for n in wnames]+[(provider,n)for provider,n in PROVIDERS.items()]
 if a.syntax_only:
  selected=a.syntax_unit or ['wlan:ieee80211','wlan:ieee80211_wireless','wlan:ieee80211_output']
  units=[tuple(x.split(':',1))for x in selected]
  assert all((c=='qdrv'and n in qnames)or(c=='wlan'and n in wnames)or PROVIDERS.get(c)==n for c,n in units)
 protected={Path(__file__),Path(qb.__file__),Path(wb.__file__),Path(qb.context.__file__),a.candidate/'result.json',qsrc/'Makefile',wb.OLD/'Makefile',a.qdrv_baseline_build/'dependencies.symvers',a.wlan_baseline_build/'dependencies.symvers',qb.context.CONTEXT/'scripts/mod/modpost',qb.context.CONTEXT/'scripts/module.lds',qb.context.CONTEXT/'Module.symvers',qb.context.CONTEXT/'.config'}
 # Directsource/header trees only; compatibility subtree is small and relevant.
 for root in(qsrc,wsrc,headers):
  protected.update(x for x in root.rglob('*')if x.is_file()and x.suffix in('.c','.h'))
 depfiles=list((a.qdrv_baseline_build/'baseline').glob('*.d'))+list((a.wlan_baseline_build/'a').glob('*.d'))
 # Provider pre-existing Kbuilddeps declare the exact generated/kernel/GPLclosure.
 for c,n in units:
  cmdfile=(qb.context.OLD if c=='qdrv'else wb.OLD)/('.'+n+'.o.cmd')
  if c=='qdrv'and not cmdfile.exists():cmdfile=qb.context.OLD/'.qdrv_hostlink.o.cmd'
  protected.add(cmdfile)
  dep=cmdfile.parent/('.'+n+'.o.d')
  if dep.exists():depfiles.append(dep)
  for line in cmdfile.read_text().splitlines()[1:]:
   value=line.strip().removesuffix('\\').strip()
   if value and not value.startswith(('$','deps_','source_'))and' 'not in value and':'not in value:
    value=value.replace('/home/user/mitrastar-linux-5.10.260',str(qb.context.KERNEL));path=Path(value)if value.startswith('/')else qb.context.CONTEXT/value
    if path.is_file():protected.add(path)
 for depfile in depfiles:
  protected.add(depfile)
  for value in readdeps(depfile):
   value=value.replace('/home/user/mitrastar-linux-5.10.260',str(qb.context.KERNEL));path=Path(value)if value.startswith('/')else qb.context.CONTEXT/value
   if path.is_file():protected.add(path)
 for tool in('gcc','ld','objcopy','nm'):protected.add(Path(str(qb.context.TC)+tool))
 for provider in ['qdrv','wlan',*PROVIDERS]:
  cmdfile=(qb.context.OLD if provider=='qdrv'else wb.OLD)/('.'+provider+'.mod.o.cmd')
  if cmdfile.exists():protected.add(cmdfile)
 pinmap={str(x):sha(x)for x in protected};canonical={key(x)for x in protected}
 a.output.mkdir(parents=True,exist_ok=False);(a.output/'input-pins.json').write_text(json.dumps(pinmap,indent=2)+'\n')
 result=dict(schema='openmitrastar.typed-header-closure/v1',status='NO_GO_TYPED_HEADER_CLOSURE',hardware_accessed=False,firmware_eligible=False,candidate=str(a.candidate),candidate_schema=proof.get('schema'),syntax_only=a.syntax_only,units=[],modules=[],no_baseline_objects_reused=True,limits='Sourcecompile/linkclosure only; exhaustiveABI/deltaverification andphysicalgates separate')
 try:
  for lane in(range(a.lanes)if not a.syntax_only else range(1)):
   label=chr(ord('a')+lane)
   def unit(pair):
    component,name=pair;folder=a.output/label/component;folder.mkdir(parents=True,exist_ok=True);cmd,source=compile_command(component,name,folder,qsrc,wsrc,headers);run(cmd,qb.context.CONTEXT,folder/('compile-'+name));dependencies=readdeps(folder/(name+'.d'));missing={key(Path(x)if x.startswith('/')else qb.context.CONTEXT/x)for x in dependencies}-canonical
    assert not missing,'unpinneddependencies '+str(sorted(missing))
    (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in dependencies)+'\n')
    row=dict(lane=label,component=component,name=name,source_sha256=sha(source),object_sha256=sha(folder/(name+'.o')));print(json.dumps(row),flush=True);return row
   with ThreadPoolExecutor(max_workers=a.jobs)as pool:result['units'].extend(pool.map(unit,units))
   if a.syntax_only:continue
   for component,names in [('qdrv',qnames),('wlan',wnames),*[(c,[n])for c,n in PROVIDERS.items()]]:
    folder=a.output/label/component;objects=[str(folder/(n+'.o'))for n in names];(folder/(component+'.mod')).write_text('\n'.join(objects)+'\n');run([str(qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/(component+'.o')),*objects],folder,folder/'link-relocatable');depsfile=a.qdrv_baseline_build/'dependencies.symvers'if component=='qdrv'else a.wlan_baseline_build/'dependencies.symvers';run([str(qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(depsfile),'-o',str(folder/'Module.symvers'),str(folder/(component+'.o'))],folder,folder/'modpost');cmd,_=compile_command(component,component+'.mod',folder,qsrc,wsrc,headers,True);run(cmd,qb.context.CONTEXT,folder/'compile-metadata');run([str(qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(qb.context.CONTEXT/'scripts/module.lds'),'-o',str(folder/(component+'.ko')),str(folder/(component+'.o')),str(folder/(component+'.mod.o'))],folder,folder/'link-module');module=folder/(component+'.ko');result['modules'].append(dict(lane=label,component=component,path=str(module),sha256=sha(module),bytes=module.stat().st_size))
  for path,h in pinmap.items():assert sha(path)==h,'pinchanged '+path
  if not a.syntax_only and a.lanes==2:
   for component in ['qdrv','wlan',*PROVIDERS]:assert sha(a.output/'a'/component/(component+'.ko'))==sha(a.output/'b'/component/(component+'.ko')),component
  result.update(status='PASS_ACTUAL_TYPED_HEADER_SYNTAX_UNITS'if a.syntax_only else 'PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA',inputs_unchanged=True,reproducible=(a.lanes==2 and not a.syntax_only),complete_closure_modules=0 if a.syntax_only else 7)
 except Exception as exc:result['error']=str(exc)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True);return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
