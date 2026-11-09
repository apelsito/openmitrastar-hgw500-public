"""Pair-package integrated userland, common49modules, R26 and compact Doom in RAM.

No 5GHz auto-load/admission, flash, reboot, UART or network operations. The
initramfs carries private per-device identity and remains local with mode0700.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,re,shutil,struct,subprocess,zlib
HERE=Path(__file__).resolve().parent
WORKSPACE=Path('/workspace/user-home/Desktop/MitraStar')
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
COMMON=BASE/'radio73-common-r3-context-v1'
NATIVE=BASE/'radio73-common-r3-r26-native-v1'
R2=BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z'
FIT=BASE/'radio73-common-product-fit-v1'
EPOCH='1792365298'
PRIVATE=('server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def output(cmd):return subprocess.check_output(cmd,text=True,stderr=subprocess.DEVNULL)
def run(cmd,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as stream:subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
 require(not a.output.exists(),'Immutable output exists');os.umask(0o077);a.output.mkdir(mode=0o700)
 c=json.loads((COMMON/'result.json').read_text());n=json.loads((NATIVE/'result.json').read_text())
 require(c['status']=='PASS_PAIRED_COMMON_KERNEL_REALTEK_ETHERNET_R24_22_NATIVE_ABI','Common kernel unqualified')
 require(n['status']=='PASS_R26_NATIVE_PAIR_ON_THIS_COMMON_KERNEL','R26/common native unqualified')
 tc=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
 require(sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263','Compiler identity changed')
 env=os.environ|{'SOURCE_DATE_EPOCH':EPOCH,'KBUILD_BUILD_TIMESTAMP':'@'+EPOCH,'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73common','KBUILD_BUILD_VERSION':'1'}
 root=a.output/'initramfs/root';root.parent.mkdir()
 shutil.copytree(FIT/'root',root,symlinks=True)
 # Capacity root uses canonical /lib/modules; the RAM supervisor requires the
 # nineteen fixed paths below. Move every common module once, never duplicate.
 commonmods=root/'lib/modules'/c['release'];mods=root/'modules';mods.mkdir()
 five=mods/'radio5g-r26';five.mkdir()
 native_names=set(json.loads((NATIVE/'pair/result.json').read_text())['lanes'][0]['modules'])
 for p in list(commonmods.iterdir()):
  if p.name=='qtn-topaz-emac-eth73.ko':p.rename(root/p.name)
  elif p.name in native_names:p.rename(five/p.name)
  else:p.rename(mods/p.name)
 commonmods.rmdir();(root/'lib/modules').rmdir()
 require(len(list(mods.glob('*.ko')))==26 and len(list(five.glob('*.ko')))==22,'Module layout count mismatch')
 (root/'etc/openmitrastar/release').write_text('OPENMITRASTAR_PRODUCT_VERSION=lyoko-linux73-common-ram-r3\nOPENMITRASTAR_BUILD_ID=common-r3-r26-doomxz\n')
 init_source=R2/'init-integrated-r2.c'
 text=init_source.read_text().replace('OPENMITRASTAR_RADIOETH73_INTEGRATED_R2','OPENMITRASTAR_RADIOETH73_COMMON_R3')
 (a.output/'init-common-r3.c').write_text(text)
 run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Werror','-Wl,-e,_start','-Wl,--build-id=none','-o',str(root/'init'),str(a.output/'init-common-r3.c')],a.output/'init.log',env)
 (root/'init').chmod(0o755)
 for p in root.rglob('*'):
  if p.is_file() and not p.is_symlink() and any(k in p.relative_to(root).as_posix() for k in PRIVATE):require(p.stat().st_mode&0o777==0o600,'Private mode differs')
 spec=importlib.util.spec_from_file_location('r2',HERE/'build_integrated_r2.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 helper.normalize_times(root);listing=a.output/'initramfs/list';helper.write_cpio_list(root,listing)
 lines=[];lanes=[]
 parent=BASE/'radioeth73-events-artifact-v1/radioeth73-events-a.ras.bin'
 require(sha(parent)=='9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e','Parent RAS template changed')
 manifest={'status':'RUNNING_COMMON_RAM_PAIR','hardware_accessed':False,'physical_boot':'UNRUN','SRAM_registered':False,'radio5g_activation':False,'classification':'RAM_DIAGNOSTIC_NO_FLASH','common_context_sha256':sha(COMMON/'result.json'),'R26_native_sha256':sha(NATIVE/'result.json'),'fit_receipt_sha256':sha(FIT/'result.json'),'lanes':[]}
 (a.output/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
 try:
  for lane in ['a','b']:
   build=a.output/lane
   run(['cp','-a','--reflink=auto',str(COMMON/lane/'kernel'),str(build)],a.output/('copy-'+lane+'.log'),env)
   config=(build/'.config').read_text()
   config=re.sub(r'CONFIG_INITRAMFS_SOURCE="[^"]*"','CONFIG_INITRAMFS_SOURCE="'+str(listing)+'"',config)
   (build/'.config').write_text(config)
   make=['make','-C',str(COMMON/'kernel-source'),'O='+str(build),'ARCH=arc','CROSS_COMPILE='+tc]
   run(make+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
   # Retain compile prefix from the qualified common lane. An initramfs path is
   # the only kernel config delta; common module hashes must remain identical.
   prefix=str(COMMON/lane)
   flags='-ffile-prefix-map='+prefix+'=/radio73-common-build -fmacro-prefix-map='+prefix+'=/radio73-common-build'
   run(make+['KCFLAGS='+flags,'-j6','vmlinux','modules','dtbs'],a.output/('kernel-'+lane+'.log'),env)
   original={p.name:sha(p) for p in (COMMON/lane/'kernel').rglob('*.ko')}
   actual={p.name:sha(p) for p in build.rglob('*.ko')}
   require(actual==original,'Common base module hashes changed during initramfs packaging')
   require(not output([tc+'nm','-u',str(build/'vmlinux')]).strip(),'Unresolved kernel imports')
   require(not re.search(r'\t(?:swape|llock|scond)(?:\t| )',output([tc+'objdump','-d',str(build/'vmlinux')])),'Forbidden kernel ISA')
   symbols={l.split()[-1]:int(l.split()[0],16) for l in output([tc+'nm',str(build/'vmlinux')]).splitlines() if len(l.split())==3}
   entry=symbols['res_service'];require(symbols['stext']==entry+8 and 0x8493a000<entry<symbols['_end']<0x88000000,'RAM entry/end contract failed')
   dtb=build/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb';require(sha(dtb)==c['lanes'][0]['dtb_sha256'],'Per-unit DTB changed')
   raw=a.output/('kernel-'+lane+'.raw');subprocess.run([tc+'objcopy','-O','binary',str(build/'vmlinux'),str(raw)],check=True)
   payload=raw.read_bytes();require(0x83002000+len(payload)<0x84000000,'RAM staging capacity exceeded')
   values=[0x27051956,0,int(EPOCH),len(payload),0x8493a000,entry,zlib.crc32(payload)&0xffffffff,5,0x13,2,0,b'OpenMitraStar7.3 COMMON R3 RAM'.ljust(32,b'\0')]
   values[1]=zlib.crc32(struct.pack('>7I4B32s',*values))&0xffffffff
   data=struct.pack('>7I4B32s',*values)+parent.read_bytes()[64:8192]+payload
   image=a.output/('radio73-common-r3-'+lane+'-RAM-ONLY.ras.bin');image.write_bytes(data)
   row={'lane':lane,'kernel_sha256':sha(build/'vmlinux'),'image_sha256':sha(image),'image_bytes':len(data),'image_crc32':f'{zlib.crc32(data)&0xffffffff:08x}','raw_sha256':sha(raw),'payload_bytes':len(payload),'load':'0x8493a000','entry':hex(entry),'end':hex(symbols['_end']),'config_sha256':sha(build/'.config'),'dtb_sha256':sha(dtb)}
   lanes.append(row);manifest['lanes']=lanes;(a.output/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
  for key in ['kernel_sha256','image_sha256','raw_sha256','config_sha256','dtb_sha256']:require(lanes[0][key]==lanes[1][key],'Common RAM pair differs: '+key)
  manifest.update(status='PASS_PAIRED_COMMON_RAM_R3_R26_DOOMXZ_PHYSICAL_UNRUN',module_count=49,game_bytes=sum(p.stat().st_size for p in (root/'www/Doom').iterdir()),kernel_release=c['release'],userland_non_sensitive=[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink() and not any(k in p.relative_to(root).as_posix() for k in PRIVATE)],limits=['RAM diagnostic only: no persistent root/store/flash image.','5GHz modules and exact carriers included, but pool CLOSED and no auto-load/start; board/provider contract not implemented.','No physical boot/association/traffic or TLS acceptance for this image.','All existing radio evidence belongs to earlier image; repeat after common ABI change.'])
 except BaseException as error:
  manifest.update(status='STOP_COMMON_RAM_BUILD',error_type=type(error).__name__,error=str(error));raise
 finally:
  manifest['builder_sha256']=sha(Path(__file__));(a.output/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
  print(json.dumps({'status':manifest['status'],'lanes':lanes}),flush=True)
if __name__=='__main__':main()
