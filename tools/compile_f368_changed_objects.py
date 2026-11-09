"""Cross-compile changed F368 C units using retained ARC flags and context.

The historical WSL source tree no longer exists. This gate reconstructs Linux
5.10.260 headers plus the local port overlay and retains generated F363 config.
It does not qualify a linked module or firmware image for installation.
"""
import argparse
from pathlib import Path
import hashlib
import json
import shlex
import shutil
import subprocess

ROOT = Path('/workspace/user-home/Desktop/MitraStar')
KERNEL = Path('/home/rea/openmitrastar-f368-build-20261021/linux-5.10.260')
CONTEXT = Path('/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z/kernel')
SOURCE = ROOT/'work/kernel-port/f368-txpower-ack/qdrv/qdrv'
BASE = ROOT/'work/kernel-port/f367r9-transition-observation/qdrv/qdrv'
OLD = ROOT/'work/linux510-radio-port/quantenna/qdrv'
TC = ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    records=[]
    for lane,source in [('baseline',BASE),('candidate',SOURCE)]:
        folder=args.output/lane;folder.mkdir()
        for name in ('qdrv_hostlink','qdrv_wlan'):
            cmdfile=OLD/('.'+name+'.o.cmd')
            args_native=shlex.split(cmdfile.read_text().splitlines()[0].split(' := ',1)[1])
            replacement=[]
            for arg in args_native:
                arg=arg.replace('/home/user/mitrastar-linux-5.10.260',str(KERNEL))
                arg=arg.replace(str(OLD),str(source))
                if arg.startswith('-Wp,-MMD,'):
                    arg='-Wp,-MMD,'+str(folder/(name+'.d'))
                if arg in ('-I./arch/arc/include/generated','-I./include','-I./arch/arc/include/generated/uapi','-I./include/generated/uapi'):
                    arg='-I'+str(CONTEXT/arg[4:])
                replacement.append(arg)
            index=replacement.index('-o');replacement[index+1]=str(folder/(name+'.o'))
            # The nested F367 source's OEM and compatibility roots are passed
            # explicitly, retaining the actual port headers over OEM headers.
            include_index=replacement.index('-c')
            includes=['-I'+str(OLD/'compat/include'),'-I'+str(ROOT/'work/sources/Quantenna-GPL'),'-I'+str(ROOT/'work/sources/Quantenna-GPL/drivers'),'-I'+str(ROOT/'work/sources/Quantenna-GPL/include'),'-I'+str(ROOT/'work/sources/Quantenna-GPL/drivers/include/shared'),'-I'+str(ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel'),'-I'+str(ROOT/'work/sources/Quantenna-GPL/common')]
            replacement[include_index:include_index]=includes
            proc=subprocess.run(replacement,cwd=CONTEXT,capture_output=True)
            (folder/(name+'.stdout')).write_bytes(proc.stdout);(folder/(name+'.stderr')).write_bytes(proc.stderr)
            row={'lane':lane,'unit':name,'exit_code':proc.returncode,'command':replacement,'retained_command_sha256':sha(cmdfile),'source_sha256':sha(source/(name+'.c'))}
            if proc.returncode==0:
                row.update(bytes=(folder/(name+'.o')).stat().st_size,sha256=sha(folder/(name+'.o')))
            records.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='command'}),flush=True)
            if proc.returncode:
                print(proc.stderr.decode()[-4000:],flush=True)
                break
        if records[-1]['exit_code']:
            break
    result={'schema':'openmitrastar.f368-changed-object-build/v1','status':'PASS_OBJECT_COMPILE_ONLY' if len(records)==4 and all(r['exit_code']==0 for r in records) else 'FAIL_HEADER_CONTEXT_RECONSTRUCTION','units':records,'kernel_source':str(KERNEL),'kernel_config_sha256':sha(CONTEXT/'.config'),'firmware_eligible':False,'linked_module_qualified':False,'hardware_accessed':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return 0 if result['status']=='PASS_OBJECT_COMPILE_ONLY' else 1

if __name__=='__main__':
    raise SystemExit(main())
