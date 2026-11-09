"""Rebuild complete CGQ baseline and bounded provider/consumer pair twice offline.

Retained ARC commands, exact generated F363 ABI and original symbol providers.
Baseline full reconstruction gates both modules before new pair closure. New
output only. No hardware, image packaging, secret or runtime operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

import compile_f368_changed_objects as ctx
from qualify_f370_qdrv_module import Elf, baseline_compare

ROOT=ctx.ROOT
OLD=ROOT/'work/linux510-radio-port/quantenna/platform/topaz'
BASE=ROOT/'work/linux510-radio-port/quantenna-f344-peers/platform/topaz'
SYMVERS=Path('/workspace/OpenMitraStar-build/f364/f364-lifetime-20260921T204704Z/dependencies.symvers')
EXPECTED={'switch_tqe':'bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f','topaz_congest_queue':'7b9954072e197b04936ed60a51ecbe813f24978d688c52ccc0d2c047f7f49611'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def command(name,source,folder):
    original=shlex.split((OLD/('.'+name+'.o.cmd')).read_text().splitlines()[0].split(' := ',1)[1])
    result=[]
    for arg in original:
        arg=arg.replace('/home/user/mitrastar-linux-5.10.260',str(ctx.KERNEL))
        if arg in ('-I./arch/arc/include/generated','-I./include','-I./arch/arc/include/generated/uapi','-I./include/generated/uapi'):arg='-I'+str(ctx.CONTEXT/arg[4:])
        if arg.startswith('-Wp,-MMD,'):arg='-Wp,-MMD,'+str(folder/(name+'.d'))
        result.append(arg)
    result[result.index('-o')+1]=str(folder/(name+'.o'))
    result[-1]=str(folder/(name+'.c') if name.endswith('.mod') else source/(name+'.c'))
    result[1:1]=['-I'+str(source),'-ffile-prefix-map='+str(source)+'='+str(OLD),'-ffile-prefix-map='+str(folder)+'=/omtqe-provider-build']
    return result

def run(argv,cwd,log):
    log.with_suffix('.command.json').write_text(json.dumps(argv,indent=2)+'\n')
    proc=subprocess.run(argv,cwd=cwd,capture_output=True,timeout=180)
    log.with_suffix('.stdout').write_bytes(proc.stdout);log.with_suffix('.stderr').write_bytes(proc.stderr)
    if proc.returncode:raise ValueError(log.name+': '+proc.stderr.decode(errors='replace')[-3000:])

def symbols(p):
    e=Elf(p)
    return {s['name']for s in e.syms if s['section']==0 and s['name']},{s['name'][10:]for s in e.syms if s['name'].startswith('__ksymtab_')}

def metadata(p):
    r={}
    for v in Elf(p).byname['.modinfo']['data'].split(b'\0'):
        if b'=' in v:
            k,x=v.decode().split('=',1);r.setdefault(k,[]).append(x)
    return {k:sorted(v)for k,v in r.items()}

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.relative_to(ROOT/'outputs/rea')
    proof=json.loads((a.candidate/'result.json').read_text())
    for n,h in proof['files'].items():assert sha(a.candidate/n)==h,n
    for name,h in EXPECTED.items():assert sha(OLD/(name+'.ko'))==h,name
    protected={Path(__file__),ROOT/'tools/compile_f368_changed_objects.py',ROOT/'tools/qualify_f370_qdrv_module.py',ctx.CONTEXT/'.config',ctx.CONTEXT/'Module.symvers',SYMVERS,ctx.CONTEXT/'scripts/module.lds',ctx.CONTEXT/'scripts/mod/modpost'}
    protected.update(x for x in a.candidate.iterdir()if x.is_file())
    for name in EXPECTED:
        protected.update((OLD/(name+'.ko'),BASE/(name+'.c'),OLD/('.'+name+'.o.cmd'),OLD/('.'+name+'.mod.o.cmd')))
        for part in (name,name+'.mod'):
            for line in (OLD/('.'+part+'.o.cmd')).read_text().splitlines()[1:]:
                token=line.strip().removesuffix('\\').strip()
                if not token or token.startswith(('$','deps_','source_'))or':'in token or' 'in token:continue
                token=token.replace('/home/user/mitrastar-linux-5.10.260',str(ctx.KERNEL))
                path=Path(token)if token.startswith('/')else ctx.CONTEXT/token
                if path.is_file():protected.add(Path(os.path.abspath(path)))
    for tree in('include/generated','include/config','arch/arc/include/generated'):protected.update(x for x in(ctx.CONTEXT/tree).rglob('*')if x.is_file())
    for name in('gcc','ld','nm','objcopy'):protected.add(Path(str(ctx.TC)+name))
    pins={str(x):sha(x)for x in protected}
    canon={os.path.abspath(x)for x in pins}
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result={'schema':'openmitrastar.tqe-cgq-bounded-provider-pair-build/v1','status':'NO_GO_OFFLINE_PAIR','hardware_accessed':False,'firmware_eligible':False,'physical_gates':'UNRUN','modules':[],'limits':'Complete offline pair linkage only; retained recovery, ledger saturation, HBM waits and foreign hardware writers remain unqualified.'}
    try:
        dep=a.output/'dependencies.symvers';dep.write_text((ctx.CONTEXT/'Module.symvers').read_text()+SYMVERS.read_text())
        def compile_module(name,source,folder,dependencies):
            folder.mkdir(parents=True,exist_ok=False)
            run(command(name,source,folder),ctx.CONTEXT,folder/'compile-source')
            deps=(folder/(name+'.d')).read_text().split(':',1)[1].replace('\\\n',' ').split()
            missing={os.path.abspath(x if x.startswith('/')else ctx.CONTEXT/x)for x in deps}-canon
            assert not missing,'unpinned deps '+str(missing)
            (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source/(name+'.c'))+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+x+' \\\n'for x in deps)+'\n')
            (folder/(name+'.mod')).write_text(str(folder/(name+'.o'))+'\n')
            run([str(ctx.CONTEXT/'scripts/mod/modpost'),'-e','-i',str(dependencies),'-o',str(folder/'Module.symvers'),str(folder/(name+'.o'))],folder,folder/'modpost')
            run(command(name+'.mod',source,folder),ctx.CONTEXT,folder/'compile-metadata')
            module=folder/(name+'.ko')
            run([str(ctx.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(ctx.CONTEXT/'scripts/module.lds'),'-o',str(module),str(folder/(name+'.o')),str(folder/(name+'.mod.o'))],folder,folder/'link-module')
            return module
        baseline={}
        for name in EXPECTED:
            module=compile_module(name,BASE,a.output/'baseline'/name,dep)
            compared=baseline_compare(Elf(OLD/(name+'.ko')),Elf(module))
            (a.output/('baseline-'+name+'.json')).write_text(json.dumps(compared,indent=2)+'\n')
            assert compared['status']=='PASS_FULL_BASELINE_RECONSTRUCTION',compared['errors']
            assert sha(module)==EXPECTED[name],'baseline wholehash '+name
            baseline[name]=dict(sha256=sha(module),bytes=module.stat().st_size,functions=compared['function_count'],relocations=compared['relocations_total'],symbols=compared['symbols_total'])
        for lane in('a','b'):
            provider=compile_module('topaz_congest_queue',a.candidate,a.output/lane/'topaz_congest_queue',dep)
            provider_imports,provider_exports=symbols(provider)
            assert not any(x.startswith('omtqe_')for x in provider_imports),'provider imports consumer'
            merged=a.output/lane/'pair-dependencies.symvers'
            names=provider_exports
            rows=[line for line in dep.read_text().splitlines()if line.strip()and line.split()[1]not in names]
            merged.write_text('\n'.join(rows)+'\n'+(provider.parent/'Module.symvers').read_text())
            consumer=compile_module('switch_tqe',a.candidate,a.output/lane/'switch_tqe',merged)
            imports,exports=symbols(consumer)
            assert not any(x.startswith('omtqe_')for x in exports),'consumer owns provider export'
            required={x for x in imports if x.startswith('omcgq_')};assert required<=provider_exports
            for name,module in(('topaz_congest_queue',provider),('switch_tqe',consumer)):
                result['modules'].append({'lane':lane,'name':name,'path':str(module),'bytes':module.stat().st_size,'sha256':sha(module),'metadata':metadata(module)})
        for name in EXPECTED:assert sha(a.output/'a'/name/(name+'.ko'))==sha(a.output/'b'/name/(name+'.ko')),'nonreproducible '+name
        for path,h in pins.items():assert sha(path)==h,'pin drift '+path
        result.update(status='PASS_OFFLINE_COMPLETE_BOUNDED_PROVIDER_PAIR_PENDING_FIXTURE_AND_DELTA',baseline=baseline,reproducible=True,pins_verified=len(pins),provider_imports_consumer=False,private_provider_exports=len([x for x in provider_exports if x.startswith('omcgq_')]))
    except Exception as ex:result['error']=str(ex)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return int(not result['status'].startswith('PASS_OFFLINE_'))

if __name__=='__main__':raise SystemExit(main())
