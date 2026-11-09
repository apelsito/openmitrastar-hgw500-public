"""Rebuild only qdrv F368 with recovered headers and pinned F363 ABI.

Offline only. Emits a new module and symbol audit; no image, installer or
hardware operation. Failed attempts keep their own evidence directories.
"""
import argparse
import concurrent.futures
from pathlib import Path
import hashlib,json,re,shlex,subprocess
import compile_f368_changed_objects as context

ROOT=context.ROOT;SOURCE=context.SOURCE;CONTEXT=context.CONTEXT;KERNEL=context.KERNEL;TC=context.TC
PARENT=Path('/workspace/OpenMitraStar-build/f367r9/f367r9-completed-20260922T224254Z')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(command,cwd,log):
    result=subprocess.run(command,cwd=cwd,capture_output=True)
    log.with_suffix('.stdout').write_bytes(result.stdout);log.with_suffix('.stderr').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError(str(log)+': '+result.stderr.decode()[-1800:])
    return result

def compile_command(name,folder,mod=False):
    old=context.OLD;template=old/('.qdrv.mod.o.cmd' if mod else '.qdrv_hostlink.o.cmd')
    command=shlex.split(template.read_text().splitlines()[0].split(' := ',1)[1])
    result=[]
    for arg in command:
        arg=arg.replace('/home/user/mitrastar-linux-5.10.260',str(KERNEL)).replace(str(old),str(SOURCE))
        arg=arg.replace('qdrv_hostlink',name)
        if arg.startswith('-Wp,-MMD,'):arg='-Wp,-MMD,'+str(folder/(name+'.d'))
        if arg in ('-I./arch/arc/include/generated','-I./include','-I./arch/arc/include/generated/uapi','-I./include/generated/uapi'):arg='-I'+str(CONTEXT/arg[4:])
        result.append(arg)
    result[result.index('-o')+1]=str(folder/(name+'.o'))
    result[-1]=str(folder/(name+'.c') if mod else SOURCE/(name+'.c'))
    inc=['-I'+str(context.OLD/'compat/include')]
    inc+=['-I'+str(ROOT/'work/sources/Quantenna-GPL'/rel) for rel in ('','drivers','include','drivers/include/shared','drivers/include/kernel','common')]
    inc+=['-ffile-prefix-map='+str(SOURCE)+'=/workspace/user-home/Desktop/MitraStar/work/linux510-radio-port/quantenna/qdrv','-ffile-prefix-map='+str(folder)+'=/f368-output']
    result[result.index('-c'):result.index('-c')]=inc
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    make=(SOURCE/'Makefile').read_text();block=make.split('qdrv-objs :=',1)[1].split('obj-m',1)[0].replace('\\',' ');names=[x[:-2] for x in block.split() if x.endswith('.o')]
    dependencies=(CONTEXT/'Module.symvers').read_text()+(PARENT/'peer-build.symvers').read_text()+(PARENT/'a/wlan.symvers').read_text()+Path('/workspace/OpenMitraStar-build/f367r7/f367r7-clock-20260922T193754Z/a/provider.symvers').read_text()
    sym=a.output/'dependencies.symvers';sym.write_text(dependencies)
    result={'schema':'openmitrastar.f368-qdrv-module/v1','status':'BUILD_STARTED','hardware_accessed':False,'firmware_eligible':False,'parent_qdrv_sha256':sha(PARENT/'a/qdrv.ko'),'source_pins':{str(p):sha(p) for p in SOURCE.rglob('*') if p.is_file()},'kernel_config_sha256':sha(CONTEXT/'.config'),'retained_kernel_symvers_sha256':sha(CONTEXT/'Module.symvers'),'source_archive_sha256':sha(KERNEL.parent/'linux-5.10.260.tar.xz')}
    try:
        modules=[]
        for lane in ('a','b'):
            folder=a.output/lane;folder.mkdir()
            def unit(name):
                command=compile_command(name,folder);run(command,CONTEXT,folder/name)
                depfile=folder/(name+'.d')
                dependencies=depfile.read_text().split(':',1)[1].replace('\\\n',' ').split()
                (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(SOURCE/(name+'.c'))+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+p+' \\\n' for p in dependencies)+'\n')
                return name
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                for name in pool.map(unit,names):print(json.dumps({'lane':lane,'compiled':name}),flush=True)
            objects=[str(folder/(name+'.o')) for name in names]
            (folder/'qdrv.mod').write_text('\n'.join(objects)+'\n')
            run([str(TC)+'ld','-r','--build-id=sha1','-o',str(folder/'qdrv.o'),*objects],folder,folder/'link-relocatable')
            run([str(CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(sym),'-o',str(folder/'Module.symvers'),str(folder/'qdrv.o')],folder,folder/'modpost')
            run(compile_command('qdrv.mod',folder,True),CONTEXT,folder/'compile-metadata')
            run([str(TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(CONTEXT/'scripts/module.lds'),'-o',str(folder/'qdrv.ko'),str(folder/'qdrv.o'),str(folder/'qdrv.mod.o')],folder,folder/'link-module')
            modules.append({'path':str(folder/'qdrv.ko'),'bytes':(folder/'qdrv.ko').stat().st_size,'sha256':sha(folder/'qdrv.ko')})
        if modules[0]['sha256']!=modules[1]['sha256']:raise RuntimeError('module builds differ')
        def undefined(path):return sorted(line.split()[-1] for line in subprocess.check_output([str(TC)+'nm','-u',str(path)],text=True).splitlines() if line.strip())
        old_imports=undefined(PARENT/'a/qdrv.ko');new_imports=undefined(a.output/'a/qdrv.ko')
        if old_imports!=new_imports:raise RuntimeError('module imports changed')
        old_exports=sorted(row.split()[1] for row in (PARENT/'a/qdrv.symvers').read_text().splitlines())
        new_exports=sorted(row.split()[1] for row in (a.output/'a/Module.symvers').read_text().splitlines())
        if old_exports!=new_exports:raise RuntimeError('module exports changed')
        for p,h in result['source_pins'].items():
            if sha(p)!=h:raise RuntimeError('source drift '+p)
        result.update(status='PASS_OFFLINE_QDRV_MODULE',modules=modules,reproducible=True,imports_unchanged=len(new_imports),exports_unchanged=len(new_exports),physical_gates='UNRUN',firmware_image_built=False)
    except Exception as error:result.update(status='BUILD_FAILED',error=str(error))
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_pins'}),flush=True);return int(result['status']!='PASS_OFFLINE_QDRV_MODULE')

if __name__=='__main__':raise SystemExit(main())
