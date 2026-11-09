"""Reuse the 5.10 Topaz reset sequence in a separate paired 7.3 RAM build."""
from pathlib import Path
import hashlib,json,os,re,subprocess,struct,zlib

BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
ROOT=Path('/workspace/user-home/Desktop/MitraStar')
PARENT=BASE/'radioeth73-events-ram-v2'
OUT=BASE/'topaz73-restart-ram-v1'
TC=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
EPOCH=1792365298

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,log,env=None):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)

def main():
 if OUT.exists():raise RuntimeError('Immutable build already exists')
 OUT.mkdir(mode=0o700)
 old=ROOT/'work/kernel-port/linux-5.10/arch/arc/kernel/reset.c'
 assert sha(old)=='b8a2dd53ec600223f0bc53165d952c7a21ff9ee53d8f46f58fb619beb37b9f4a'
 source=OUT/'source'
 run(['cp','-a','--reflink=auto',str(PARENT/'source'),str(source)],OUT/'copy-source.log')
 reset=source/'arch/arc/kernel/reset.c'
 original=reset.read_text()
 prior=old.read_text()
 begin=prior.index('\tvoid __iomem *sysctl')
 end=prior.index('\n}\n',begin)
 body=prior[begin:end]
 begin2=original.index('\t/* Soft reset')
 end2=original.index('\n}\n',begin2)
 changed=original[:begin2]+'#ifdef CONFIG_ARC_PLAT_TOPAZ_BASIC\n'+body+'\n#else\n'+original[begin2:end2]+'\n#endif'+original[end2:]
 changed=changed.replace('#include <linux/kernel.h>','#include <linux/io.h>\n#include <linux/kernel.h>')
 reset.write_text(changed)
 # Execute the actual imported reset body with fake writel/barrier primitives.
 # Exact register sequence and values are the experiment, not guessed hardware.
 fixture=OUT/'reset-sequence-host.c'
 fixture.write_text('''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define __iomem
static unsigned n;static int barrier;
static const uintptr_t address[]={0xf4000000,0xf4000004,0xf400000c,0xe0000000,0xe0000004,0xe0000000};
static const uint32_t value[]={1,8,0x76,0xffffffff,0,0};
static void writel(uint32_t v,void*p){if(n>=6||(uintptr_t)p!=address[n]||v!=value[n])exit(3);n++;}
static void mb(void){if(n!=6)exit(4);barrier=1;}
static void cpu_relax(void){if(n!=6||!barrier)exit(5);puts("PASS_RESET_EXACT_SIX_WRITES_AND_BARRIER");exit(0);}
static void actual_restart(void){
'''+body+'\n}\nint main(void){actual_restart();return 2;}\n')
 run(['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-o',str(OUT/'reset-sequence-host'),str(fixture)],OUT/'fixture-build.log')
 run([str(OUT/'reset-sequence-host')],OUT/'fixture-run.log')
 # Show the fixture rejects an altered value, ordering and omitted barrier.
 negative=[]
 for name,before,after in [('wrong-value','writel(0x8,','writel(0x9,'),('swapped-order','writel(~0U, sysctl + 0x00);\n\twritel(0, sysctl + 0x04);','writel(0, sysctl + 0x04);\n\twritel(~0U, sysctl + 0x00);'),('no-barrier','\n\tmb();','\n\t(void)mb;')]:
  candidate=fixture.read_text();assert before in candidate
  file=OUT/(name+'.c');file.write_text(candidate.replace(before,after,1));binary=OUT/name
  run(['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-o',str(binary),str(file)],OUT/(name+'-build.log'))
  r=subprocess.run([str(binary)],capture_output=True);assert r.returncode!=0
  negative.append({'case':name,'exit':r.returncode})
 # Source trees must differ only at the restart implementation.
 differences=[];count=0
 for f in (PARENT/'source').rglob('*'):
  if not f.is_file() or f.is_symlink():continue
  other=source/f.relative_to(PARENT/'source');assert other.is_file();count+=1
  if sha(f)!=sha(other):differences.append(f.relative_to(PARENT/'source').as_posix())
 assert differences==['arch/arc/kernel/reset.c'],differences
 env=os.environ|{'SOURCE_DATE_EPOCH':str(EPOCH),'KBUILD_BUILD_TIMESTAMP':'@'+str(EPOCH),'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73','KBUILD_BUILD_VERSION':'1'}
 lanes=[]
 parent_image=(BASE/'radioeth73-events-artifact-v1/radioeth73-events-a.ras.bin').read_bytes()
 for lane in ['a','b']:
  target=OUT/lane
  run(['cp','-a','--reflink=auto',str(PARENT/lane),str(target)],OUT/('copy-'+lane+'.log'))
  assert sha(target/'.config')==sha(PARENT/lane/'.config')
  make=['make','-C',str(source),'O='+str(target),'ARCH=arc','CROSS_COMPILE='+TC]
  run(make+['KCFLAGS=-ffile-prefix-map='+str(target)+'=/radio73-build','-j6','vmlinux','dtbs'],OUT/('build-'+lane+'.log'),env)
  elf=target/'vmlinux'
  asm=subprocess.check_output([TC+'objdump','-d',str(elf)],text=True)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  assert not subprocess.check_output([TC+'nm','-u',str(elf)],text=True).strip()
  syms={line.split()[-1]:int(line.split()[0],16) for line in subprocess.check_output([TC+'nm',str(elf)],text=True).splitlines() if len(line.split())==3}
  entry=syms['res_service'];assert syms['stext']==entry+8 and syms['_end']<0x88000000
  raw=OUT/('kernel-'+lane+'.raw');subprocess.run([TC+'objcopy','-O','binary',str(elf),str(raw)],check=True)
  data=raw.read_bytes();header=[0x27051956,0,EPOCH,len(data),0x8493a000,entry,zlib.crc32(data)&0xffffffff,5,0x13,2,0,b'OpenMitraStar7.3 RESET RAM'.ljust(32,b'\0')]
  header[1]=zlib.crc32(struct.pack('>7I4B32s',*header))&0xffffffff
  image=struct.pack('>7I4B32s',*header)+parent_image[64:8192]+data;file=OUT/('topaz73-restart-'+lane+'.ras.bin');file.write_bytes(image)
  lanes.append({'lane':lane,'kernel_sha256':sha(elf),'kernel_bytes':elf.stat().st_size,'image_sha256':sha(file),'image_bytes':len(image),'image_crc32':f'{zlib.crc32(image)&0xffffffff:08x}','raw_sha256':sha(raw),'payload_bytes':len(data),'entry':hex(entry),'load':'0x8493a000','end':hex(syms['_end']),'config_sha256':sha(target/'.config'),'dtb_sha256':sha(target/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb')})
 for key in ['kernel_sha256','image_sha256','raw_sha256','config_sha256','dtb_sha256']:assert lanes[0][key]==lanes[1][key],key
 parent=json.loads((BASE/'radioeth73-events-artifact-v1/result.json').read_text())
 result=parent|{'schema':'openmitrastar.topaz73-restart-ram/v1','lanes':lanes,'parent_image_sha256':parent['lanes'][0]['image_sha256'],'change':'Only restore Topaz5.10 watchdog/sysctl machine_restart for CONFIG_ARC_PLAT_TOPAZ_BASIC','reset_reference_sha256':sha(old),'reset_parent_sha256':hashlib.sha256(original.encode()).hexdigest(),'reset_candidate_sha256':sha(reset),'source_files_checked':count,'source_differences':differences,'fixture':'PASS_EXACT_REGISTER_SEQUENCE_HOST_ONLY','negative_controls':negative,'hardware_accessed':False,'physical_restart':'UNRUN'}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'image_bytes':lanes[0]['image_bytes'],'sha256':lanes[0]['image_sha256'],'fixture':result['fixture'],'physical_restart':'UNRUN'}))
if __name__=='__main__':main()
