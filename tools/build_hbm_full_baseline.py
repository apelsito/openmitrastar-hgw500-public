"""Reproduce the complete original HBM module twice; offline and immutable.

Use retained ARC commands, generated F363 context and full ELF comparison. No
candidate changes or hardware access. The output is always a new directory.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import build_tqe_bounded_provider_pair as pair
from qualify_f370_qdrv_module import Elf, baseline_compare

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.relative_to(pair.ROOT/'outputs/rea')
    old=pair.OLD;source=pair.BASE;ctx=pair.ctx
    expected='f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8'
    assert pair.sha(old/'hbm.ko')==expected
    assert pair.sha(old/'hbm.c')==pair.sha(source/'hbm.c')
    protected={Path(__file__),Path(pair.__file__),pair.ROOT/'tools/compile_f368_changed_objects.py',pair.ROOT/'tools/qualify_f370_qdrv_module.py',ctx.CONTEXT/'.config',ctx.CONTEXT/'Module.symvers',pair.SYMVERS,ctx.CONTEXT/'scripts/module.lds',ctx.CONTEXT/'scripts/mod/modpost',old/'hbm.ko',old/'hbm.c',source/'hbm.c'}
    for part in ('hbm','hbm.mod'):
        cmd=old/('.'+part+'.o.cmd');protected.add(cmd)
        for line in cmd.read_text().splitlines()[1:]:
            token=line.strip().removesuffix('\\').strip()
            if not token or token.startswith(('$','deps_','source_'))or':'in token or' 'in token:continue
            token=token.replace('/home/user/mitrastar-linux-5.10.260',str(ctx.KERNEL))
            path=Path(token)if token.startswith('/')else ctx.CONTEXT/token
            if path.is_file():protected.add(Path(os.path.abspath(path)))
    for tree in ('include/generated','include/config','arch/arc/include/generated'):
        protected.update(x for x in(ctx.CONTEXT/tree).rglob('*')if x.is_file())
    for name in ('gcc','ld','nm','objcopy'):protected.add(Path(str(ctx.TC)+name))
    pins={str(x):pair.sha(x)for x in protected};canon={os.path.abspath(x)for x in pins}
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(schema='openmitrastar.hbm-full-baseline/v1',status='NO_GO_BASELINE_REPRODUCTION',hardware_accessed=False,firmware_eligible=False,modules=[])
    try:
        dep=a.output/'dependencies.symvers';dep.write_text((ctx.CONTEXT/'Module.symvers').read_text()+pair.SYMVERS.read_text())
        for lane in ('a','b'):
            folder=a.output/lane;folder.mkdir()
            pair.run(pair.command('hbm',source,folder),ctx.CONTEXT,folder/'compile-source')
            deps=(folder/'hbm.d').read_text().split(':',1)[1].replace('\\\n',' ').split()
            missing={os.path.abspath(x if x.startswith('/')else ctx.CONTEXT/x)for x in deps}-canon
            assert not missing,'unpinned deps '+str(missing)
            (folder/'.hbm.o.cmd').write_text('source_'+str(folder/'hbm.o')+' := '+str(source/'hbm.c')+'\n\ndeps_'+str(folder/'hbm.o')+' := \\\n'+''.join('  '+x+' \\\n'for x in deps)+'\n')
            (folder/'hbm.mod').write_text(str(folder/'hbm.o')+'\n')
            pair.run([str(ctx.CONTEXT/'scripts/mod/modpost'),'-e','-i',str(dep),'-o',str(folder/'Module.symvers'),str(folder/'hbm.o')],folder,folder/'modpost')
            pair.run(pair.command('hbm.mod',source,folder),ctx.CONTEXT,folder/'compile-metadata')
            module=folder/'hbm.ko'
            pair.run([str(ctx.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(ctx.CONTEXT/'scripts/module.lds'),'-o',str(module),str(folder/'hbm.o'),str(folder/'hbm.mod.o')],folder,folder/'link-module')
            comparison=baseline_compare(Elf(old/'hbm.ko'),Elf(module));(folder/'full-baseline-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
            assert comparison['status']=='PASS_FULL_BASELINE_RECONSTRUCTION',comparison['errors']
            assert pair.sha(module)==expected,'baseline wholehash'
            result['modules'].append(dict(lane=lane,path=str(module),bytes=module.stat().st_size,sha256=pair.sha(module),functions=comparison['function_count'],relocations=comparison['relocations_total'],symbols=comparison['symbols_total']))
        for path,h in pins.items():assert pair.sha(path)==h,'pin drift '+path
        result.update(status='PASS_FULL_HBM_BASELINE_X2_BYTE_IDENTICAL',reproducible=True,pins_verified=len(pins))
    except Exception as ex:result['error']=str(ex)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return int(not result['status'].startswith('PASS'))

if __name__=='__main__':raise SystemExit(main())
