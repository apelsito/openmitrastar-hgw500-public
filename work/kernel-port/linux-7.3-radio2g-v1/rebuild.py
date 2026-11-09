"""Rebuild radio73 from pinned pristine Linux7.3 archive and portable overlays.
All local inputs explicit; fresh output, no downloads or physical device access.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(command,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--basic',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--plan-only',action='store_true');a=p.parse_args()
 assert not a.output.exists()
 assert sha(a.archive)=='87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953'
 assert sha(a.basic/'basic73.patch')=='d36ed090cdcb9470eb301933c066b2c7cde12de3af5c1cf3d02d9a7509088192'
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 manifest=json.loads((HERE/'SOURCE_MANIFEST.json').read_text())
 for row in manifest['files']:assert sha(HERE/row['path'])==row['sha256'],row['path']
 if a.plan_only:print(json.dumps({'status':'PASS_PORTABLE_INPUT_PLAN','files':len(manifest['files']),'hardware_accessed':False}));return
 a.output.mkdir(parents=True);source_root=a.output/'source';source_root.mkdir()
 with tarfile.open(a.archive) as tar:tar.extractall(source_root,filter='data')
 source=source_root/'linux-7.3';env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='radio73',KBUILD_BUILD_VERSION='1')
 run(['patch','--batch','--fuzz=0','-p1','-d',str(source),'-i',str(a.basic/'basic73.patch')],a.output/'patch.log',env)
 for file in (HERE/'overlay').rglob('*'):
  if file.is_file():
   target=source/file.relative_to(HERE/'overlay');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
 ir=a.output/'initramfs';ir.mkdir();init_source=ir/'basic73_init_nolibc_time64_nonce.c';shutil.copyfile(a.basic/'init.c',init_source)
 run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Wl,-e,_start','-Wl,--build-id=none','-o',str(ir/'init'),str(init_source)],a.output/'init-build.log',env)
 assert sha(ir/'init')=='9380f5c7b85231ae9320fc70b7b6a922316978c61f69d473907271168ca36194'
 listing=ir/'list';listing.write_text('dir /dev 755 0 0\ndir /proc 755 0 0\ndir /sys 755 0 0\nnod /dev/console 600 0 0 c 5 1\nfile /init '+str(ir/'init')+' 755 0 0\n')
 results=[]
 for lane in ['a','b']:
  build=a.output/lane;build.mkdir();(build/'.config').write_text((HERE/'radio73.config.template').read_text().replace('@INITRAMFS_LIST@',str(listing)))
  make=['make','-C',str(source),'O='+str(build),'ARCH=arc','CROSS_COMPILE='+tc]
  run(make+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
  run(make+['KCFLAGS=-ffile-prefix-map='+str(build)+'=/radio73-build','-j6','vmlinux','dtbs','modules'],a.output/('build-'+lane+'.log'),env)
  exports={line.split()[1] for line in (build/'Module.symvers').read_text().splitlines()}
  records=[]
  for f in [build/'vmlinux']+sorted(build.rglob('*.ko')):
   asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
   imports=[l.split()[-1] for l in subprocess.check_output([tc+'nm','-u',str(f)],text=True).splitlines()]
   assert not (set(imports)-exports if f.suffix=='.ko' else imports),f
   records.append({'path':f.relative_to(build).as_posix(),'sha256':sha(f),'bytes':f.stat().st_size})
  results.append({'lane':lane,'files':records})
 assert results[0]['files']==results[1]['files'],'Independent lanes differ'
 (a.output/'result.json').write_text(json.dumps({'schema':'openmitrastar.radio73-portable-build/v1','status':'PASS_PORTABLE_PAIRED_BUILD','hardware_accessed':False,'physical':'UNRUN','lanes':results},indent=2)+'\n')
 print(json.dumps({'status':'PASS_PORTABLE_PAIRED_BUILD','artifacts_per_lane':len(results[0]['files'])}))
if __name__=='__main__':main()
