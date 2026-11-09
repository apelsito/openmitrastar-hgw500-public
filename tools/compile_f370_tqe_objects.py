"""Compile exact F365 baseline and F370 qdrv_tx twice; offline object gate."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
import compile_f368_changed_objects as context
from compare_f368_baseline_code import symbols
ROOT=context.ROOT
BASE=ROOT/'work/linux510-radio-port/quantenna-f364-lifetime/qdrv'
SOURCE=ROOT/'work/kernel-port/f370-tqe-observation/source/qdrv'
MODULE=ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3/payload/modules/qdrv.ko'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    proof=json.loads((SOURCE.parent.parent/'source-manifest.json').read_text());assert sha(MODULE)==proof['parent_module']['sha256']
    for name,digest in proof['source_pins'].items():assert sha(SOURCE.parent/name)==digest,name
    template=context.OLD/'.qdrv_tx.o.cmd';original=shlex.split(template.read_text().splitlines()[0].split(' := ',1)[1]);records=[]
    for lane,source in [('baseline',BASE),('a',SOURCE),('b',SOURCE)]:
        folder=a.output/lane;folder.mkdir();cmd=[]
        for arg in original:
            arg=arg.replace('/home/user/mitrastar-linux-5.10.260',str(context.KERNEL)).replace(str(context.OLD),str(source))
            if arg.startswith('-Wp,-MMD,'):arg='-Wp,-MMD,'+str(folder/'qdrv_tx.d')
            if arg in ('-I./arch/arc/include/generated','-I./include','-I./arch/arc/include/generated/uapi','-I./include/generated/uapi'):arg='-I'+str(context.CONTEXT/arg[4:])
            cmd.append(arg)
        cmd[cmd.index('-o')+1]=str(folder/'qdrv_tx.o');cmd[-1]=str(source/'qdrv_tx.c')
        includes=['-I'+str(context.OLD/'compat/include')]+['-I'+str(ROOT/'work/sources/Quantenna-GPL'/rel) for rel in ('','drivers','include','drivers/include/shared','drivers/include/kernel','common')]
        includes+=['-ffile-prefix-map='+str(source)+'=/workspace/user-home/Desktop/MitraStar/work/linux510-radio-port/quantenna/qdrv']
        cmd[cmd.index('-c'):cmd.index('-c')]=includes
        run=subprocess.run(cmd,cwd=context.CONTEXT,capture_output=True);(folder/'stdout').write_bytes(run.stdout);(folder/'stderr').write_bytes(run.stderr);assert run.returncode==0,run.stderr.decode()[-3500:]
        records.append(dict(lane=lane,sha256=sha(folder/'qdrv_tx.o'),bytes=(folder/'qdrv_tx.o').stat().st_size));print(json.dumps(records[-1]),flush=True)
    assert records[1]['sha256']==records[2]['sha256'],'candidate objects differ'
    index={}
    for name,code,size in symbols(MODULE):index.setdefault(name,[]).append((code,size))
    matches=[];mismatch=[];ambiguous=[]
    for name,code,size in symbols(a.output/'baseline/qdrv_tx.o'):
        possible=index.get(name,[])
        if len(possible)!=1:ambiguous.append(name);continue
        (matches if possible[0][0]==code else mismatch).append(name)
    imports=lambda file:sorted(row.split()[-1] for row in subprocess.check_output([str(context.TC)+'nm','-u',str(file)],text=True).splitlines() if row.strip())
    old=imports(a.output/'baseline/qdrv_tx.o');new=imports(a.output/'a/qdrv_tx.o');assert old==new,'new imports'
    result=dict(schema='openmitrastar.f370-object-qualification/v1',status='PASS_BASELINE_BYTES_AND_REPRODUCIBLE_OBJECTS' if not mismatch else 'BASELINE_FUNCTION_BYTES_MISMATCH',objects=records,baseline_module_sha256=sha(MODULE),baseline_matches=matches,baseline_mismatch=mismatch,ambiguous_excluded=ambiguous,imports_unchanged=len(new),kernel_config_sha256=sha(context.CONTEXT/'.config'),retained_command_sha256=sha(template),hardware_accessed=False,firmware_image=False,linked_module=False,physical='NO_GO_PHYSICAL',limits='Unambiguous ET_REL function bytes only; object success is not module/firmware/runtime acceptance.')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(bool(mismatch))
if __name__=='__main__':raise SystemExit(main())
