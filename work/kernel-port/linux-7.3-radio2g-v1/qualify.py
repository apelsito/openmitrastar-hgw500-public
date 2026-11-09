"""Independent clean O= build and ARC/module import/paired-byte qualification."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False);build=a.output/'b';build.mkdir()
 config=(a.baseline/'.config').read_bytes();(build/'.config').write_bytes(config)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-')
 env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='radio73',KBUILD_BUILD_VERSION='1')
 cmd=['make','-C',str(a.source),'O='+str(build),'ARCH=arc','CROSS_COMPILE='+tc]
 for step,extras in [('config',['olddefconfig']),('build',['KCFLAGS=-ffile-prefix-map='+str(build)+'=/radio73-build','-j6','vmlinux','dtbs','modules'])]:
  print('RUN '+step,flush=True)
  with (a.output/(step+'.log')).open('xb') as f:subprocess.run(cmd+extras,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
 assert sha(build/'.config')==sha(a.baseline/'.config')
 exports={l.split()[1] for l in (build/'Module.symvers').read_text().splitlines()}
 records=[]
 names=[Path('vmlinux')]+sorted(f.relative_to(build) for f in build.rglob('*.ko'))
 for name in names:
  f=build/name;reference=a.baseline/name
  assert sha(f)==sha(reference),str(name)+' differs'
  asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),str(name)+' forbidden extension'
  unresolved=[l.split()[-1] for l in subprocess.check_output([tc+'nm','-u',str(f)],text=True).splitlines()]
  assert not (set(unresolved)-exports if name.suffix=='.ko' else unresolved),(name,unresolved)
  records.append({'path':name.as_posix(),'bytes':f.stat().st_size,'sha256':sha(f),'identical':True,'imports_resolved':len(unresolved),'forbidden_instructions':0})
 report={'schema':'openmitrastar.radio73-independent-qualification/v1','status':'PASS_PAIRED_KERNEL_MODULE_ARC_IMPORTS','hardware_accessed':False,'clean_independent_output':True,'config_sha256':sha(build/'.config'),'files':records,'radio_physical':'UNRUN','ethernet_included_in_this_build':False}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
