"""Offline complete F365-lineage QDRV build; immutable new output only.

Reuses retained ARC flags and recovered headers, never changes pinned builders,
source/configuration, or hardware. Baseline once, F370 candidate twice. A module
build is distinct from a firmware image or physical radio acceptance.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import compile_f368_changed_objects as context

ROOT=context.ROOT
BASE=ROOT/'work/linux510-radio-port/quantenna-f364-lifetime/qdrv'
SOURCE=ROOT/'work/kernel-port/f370-tqe-observation/source/qdrv'
PARENT=Path('/workspace/OpenMitraStar-build/f364/f364-lifetime-20260921T204704Z')
MODULE=PARENT/'a/qdrv/qdrv.ko'
EXPECTED='cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01'
PARAMETERS={'openmitrastar_auc_raw_ok','openmitrastar_auc_raw_other','openmitrastar_auc_busy_free','openmitrastar_auc_return_success'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd,cwd,log):
    process=subprocess.run(cmd,cwd=cwd,capture_output=True)
    log.with_suffix('.stdout').write_bytes(process.stdout)
    log.with_suffix('.stderr').write_bytes(process.stderr)
    log.with_suffix('.command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    if process.returncode:raise RuntimeError(str(log)+': '+process.stderr.decode(errors='replace')[-2200:])
    return process.stdout

def command(name,source,folder,mod=False):
    template=context.OLD/('.qdrv.mod.o.cmd' if mod else '.'+name+'.o.cmd')
    substitute=False
    if not template.exists():template=context.OLD/'.qdrv_hostlink.o.cmd';substitute=True
    original=shlex.split(template.read_text().splitlines()[0].split(' := ',1)[1])
    output=[]
    for arg in original:
        arg=arg.replace('/home/user/mitrastar-linux-5.10.260',str(context.KERNEL)).replace(str(context.OLD),str(source))
        if substitute:arg=arg.replace('qdrv_hostlink',name)
        if arg.startswith('-Wp,-MMD,'):arg='-Wp,-MMD,'+str(folder/(name+'.d'))
        if arg in ('-I./arch/arc/include/generated','-I./include','-I./arch/arc/include/generated/uapi','-I./include/generated/uapi'):
            arg='-I'+str(context.CONTEXT/arg[4:])
        output.append(arg)
    output[output.index('-o')+1]=str(folder/(name+'.o'))
    output[-1]=str(folder/(name+'.c') if mod else source/(name+'.c'))
    includes=['-I'+str(context.OLD/'compat/include')]
    includes+=['-I'+str(ROOT/'work/sources/Quantenna-GPL'/p) for p in ('','drivers','include','drivers/include/shared','drivers/include/kernel','common')]
    includes+=['-ffile-prefix-map='+str(source)+'=/f364-qdrv/qdrv','-ffile-prefix-map='+str(folder)+'=/f370-output']
    output[output.index('-c'):output.index('-c')]=includes
    return output,template

def imports(p):
    return sorted(row.split()[-1] for row in subprocess.check_output([str(context.TC)+'nm','-u',str(p)],text=True).splitlines() if row.strip())
def modinfo(p):
    raw=subprocess.check_output([str(context.TC)+'objcopy','--dump-section','.modinfo=/dev/stdout',str(p)],stderr=subprocess.DEVNULL)
    result={}
    for value in raw.split(b'\0'):
        if b'=' in value:
            k,v=value.decode(errors='replace').split('=',1);result.setdefault(k,[]).append(v)
    return {k:sorted(v) for k,v in result.items()}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    result={'schema':'openmitrastar.f370-complete-qdrv/v1','status':'BUILD_STARTED','hardware_accessed':False,'firmware_image':False,'physical_gates':'UNRUN','firmware_eligible':False}
    try:
        assert sha(MODULE)==EXPECTED and MODULE.stat().st_size==685332,'wrong baseline module'
        manifest=ROOT/'work/kernel-port/f370-tqe-observation/source-manifest.json'
        proof=json.loads(manifest.read_text())
        for p,h in proof['source_pins'].items():assert sha(SOURCE.parent/p)==h,p
        names=[x[:-2] for x in (SOURCE/'Makefile').read_text().split('qdrv-objs :=',1)[1].split('obj-m',1)[0].replace('\\',' ').split() if x.endswith('.o')]
        protected=[manifest,MODULE,PARENT/'result.json',PARENT/'dependencies.symvers',PARENT/'a/Module.symvers',context.CONTEXT/'.config',context.CONTEXT/'Module.symvers',context.KERNEL.parent/'linux-5.10.260.tar.xz',Path(__file__)]
        protected += [p for src in (BASE,SOURCE) for p in src.rglob('*') if p.is_file()]
        protected += [context.OLD/('.'+n+'.o.cmd') for n in names if (context.OLD/('.'+n+'.o.cmd')).exists()]
        protected += [context.OLD/'.qdrv.mod.o.cmd']
        pins={str(p):sha(p) for p in protected}
        (args.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        dependencies=args.output/'dependencies.symvers'
        dependencies.write_text((context.CONTEXT/'Module.symvers').read_text()+(PARENT/'dependencies.symvers').read_text())
        modules=[]
        for lane,source in [('baseline',BASE),('a',SOURCE),('b',SOURCE)]:
            folder=args.output/lane;folder.mkdir()
            def unit(name):
                cmd,template=command(name,source,folder)
                run(cmd,context.CONTEXT,folder/name)
                deps=(folder/(name+'.d')).read_text().split(':',1)[1].replace('\\\n',' ').split()
                (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source/(name+'.c'))+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+p+' \\\n' for p in deps)+'\n')
                return name
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                for name in pool.map(unit,names):print(json.dumps({'lane':lane,'compiled':name}),flush=True)
            objects=[str(folder/(name+'.o')) for name in names]
            (folder/'qdrv.mod').write_text('\n'.join(objects)+'\n')
            run([str(context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/'qdrv.o'),*objects],folder,folder/'link-relocatable')
            run([str(context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(dependencies),'-o',str(folder/'Module.symvers'),str(folder/'qdrv.o')],folder,folder/'modpost')
            cmd,template=command('qdrv.mod',source,folder,True);run(cmd,context.CONTEXT,folder/'compile-metadata')
            run([str(context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(context.CONTEXT/'scripts/module.lds'),'-o',str(folder/'qdrv.ko'),str(folder/'qdrv.o'),str(folder/'qdrv.mod.o')],folder,folder/'link-module')
            row={'lane':lane,'path':str(folder/'qdrv.ko'),'bytes':(folder/'qdrv.ko').stat().st_size,'sha256':sha(folder/'qdrv.ko')}
            modules.append(row);print(json.dumps(row),flush=True)
        assert modules[1]['sha256']==modules[2]['sha256'],'candidate modules differ'
        old_imports=imports(MODULE)
        for row in modules:assert imports(Path(row['path']))==old_imports,'import delta '+row['lane']
        exports=lambda p:sorted(row.split()[1] for row in p.read_text().splitlines())
        old_exports=exports(PARENT/'a/Module.symvers')
        for lane in ('baseline','a','b'):assert exports(args.output/lane/'Module.symvers')==old_exports,'exports changed'
        old_info=modinfo(MODULE);base_info=modinfo(args.output/'baseline/qdrv.ko');new_info=modinfo(args.output/'a/qdrv.ko')
        (args.output/'modinfo-comparison.json').write_text(json.dumps({'parent':old_info,'baseline':base_info,'candidate':new_info},indent=2)+'\n')
        for key in ('name','vermagic','depends','license','parm','parmtype'):assert old_info.get(key)==base_info.get(key),'baseline modinfo '+key
        for key in ('name','vermagic','depends','license'):assert old_info.get(key)==new_info.get(key),'candidate modinfo '+key
        added={p.split(':',1)[0] for p in new_info.get('parmtype',[])}-{p.split(':',1)[0] for p in old_info.get('parmtype',[])}
        assert added==PARAMETERS,('parameter additions',added)
        for p,h in pins.items():assert sha(p)==h,'protected input changed '+p
        result.update(status='PASS_BUILD_PENDING_FULL_BASELINE_COMPARISON',modules=modules,reproducible=True,imports_unchanged=len(old_imports),exports_unchanged=len(old_exports),added_parameters=sorted(added),source_inputs_unchanged=True,parent_module_sha256=EXPECTED,baseline_metadata_valid=True)
    except Exception as exc:result.update(status='BUILD_FAILED',error=str(exc))
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    return int(result['status']!='PASS_BUILD_PENDING_FULL_BASELINE_COMPARISON')
if __name__=='__main__':raise SystemExit(main())
