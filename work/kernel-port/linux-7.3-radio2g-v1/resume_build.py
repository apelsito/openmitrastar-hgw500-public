"""Resume the isolated diagnostic build and retain its own new log/receipt."""
import argparse,json,os,subprocess
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='radio73',KBUILD_BUILD_VERSION='1')
 cmd=['make','-C',str(a.source),'O='+str(a.build),'ARCH=arc','CROSS_COMPILE='+str(a.toolchain/'bin/arc-snps-linux-uclibc-'),'KCFLAGS=-ffile-prefix-map='+str(a.build)+'=/radio73-build','-j6','vmlinux','dtbs','modules']
 with (a.output/'build.log').open('xb') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=1800)
 (a.output/'result.json').write_text(json.dumps({'status':'COMPILE_PASS_UNQUALIFIED' if r.returncode==0 else 'COMPILE_FAIL','exit_code':r.returncode,'hardware_accessed':False,'command':cmd},indent=2)+'\n')
 print(json.dumps({'exit_code':r.returncode,'receipt':str(a.output/'result.json')}));raise SystemExit(r.returncode)
if __name__=='__main__':main()
