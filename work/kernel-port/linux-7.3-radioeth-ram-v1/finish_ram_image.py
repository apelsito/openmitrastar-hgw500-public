"""Finish staged secure RAM image after PID1 freestanding repair; new receipt."""
import argparse,hashlib,json,os,re,shutil,struct,subprocess,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
EPOCH=1792365298
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(command,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['build','context','toolchain','template','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 b=a.build;root=b/'initramfs/root';assert root.is_dir()
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-')
 assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 env=os.environ|{'SOURCE_DATE_EPOCH':str(EPOCH),'KBUILD_BUILD_TIMESTAMP':'@'+str(EPOCH),'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73','KBUILD_BUILD_VERSION':'1'}
 init=b/'initramfs/init';run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Werror','-Wl,-e,_start','-Wl,--build-id=none','-o',str(init),str(HERE/'init-secure-v2.c')],a.output/'init-build.log',env)
 shutil.copyfile(init,root/'init');(root/'init').chmod(0o755)
 elf_files=[f for f in root.rglob('*') if f.is_file() and not f.is_symlink() and f.read_bytes().startswith(b'\x7fELF')]
 exports=set();needs={}
 for file in elf_files:
  for line in subprocess.check_output([tc+'nm','-D','--defined-only',str(file)],text=True,stderr=subprocess.DEVNULL).splitlines():
   if line.split():exports.add(line.split()[-1].split('@')[0])
 for file in elf_files:
  asm=subprocess.check_output([tc+'objdump','-d',str(file)],text=True)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),file
  if file.suffix!='.ko' and file.name!='init':
   imports={line.split()[-1].split('@')[0] for line in subprocess.check_output([tc+'nm','-D','--undefined-only',str(file)],text=True,stderr=subprocess.DEVNULL).splitlines() if line.split() and line.split()[0]=='U'}
   assert not imports-exports,(file,imports-exports)
   dyn=subprocess.check_output([tc+'readelf','-d',str(file)],text=True)
   libraries=re.findall(r'\(NEEDED\).*\[([^]]+)\]',dyn)
   assert all((root/'lib'/library).is_file() for library in libraries),(file,libraries)
   needs[file.relative_to(root).as_posix()]=libraries
 records=[];lines=[]
 private=['server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow']
 for file in sorted(root.rglob('*')):
  name='/'+file.relative_to(root).as_posix();mode=file.stat().st_mode&0o777
  if file.is_symlink():lines.append('slink '+name+' '+str(file.readlink())+' 777 0 0')
  elif file.is_dir():lines.append('dir '+name+' '+format(mode,'o')+' 0 0')
  else:lines.append('file '+name+' '+str(file)+' '+format(mode,'o')+' 0 0')
  if file.is_file() and not file.is_symlink() and not any(k in name for k in private):records.append({'path':name,'bytes':file.stat().st_size,'sha256':sha(file)})
 for name,major,minor,mode in [('console',5,1,'600'),('ttyS0',4,64,'600'),('null',1,3,'666'),('zero',1,5,'666'),('random',1,8,'444'),('urandom',1,9,'444'),('ptmx',5,2,'666')]:lines.append('nod /dev/'+name+' '+mode+' 0 0 c '+str(major)+' '+str(minor))
 listing=b/'initramfs/list';assert not listing.exists();listing.write_text('\n'.join(lines)+'\n')
 lanes=[];template=a.template.read_bytes();assert sha(a.template)=='84e4047246c3ae0a13435e9a113f08dbf30f3d0267543e58d56995189a773573'
 for lane in ['a','b']:
  out=b/lane;assert not out.exists();run(['cp','-a','--reflink=auto',str(a.context/lane),str(out)],a.output/('copy-build-'+lane+'.log'),env)
  config=(out/'.config').read_text();config=re.sub(r'CONFIG_INITRAMFS_SOURCE="[^"]*"','CONFIG_INITRAMFS_SOURCE="'+str(listing)+'"',config);(out/'.config').write_text(config)
  make=['make','-C',str(b/'source'),'O='+str(out),'ARCH=arc','CROSS_COMPILE='+tc]
  run(make+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
  run(make+['KCFLAGS=-ffile-prefix-map='+str(out)+'=/radio73-build','-j6','vmlinux','dtbs'],a.output/('build-'+lane+'.log'),env)
  elf=out/'vmlinux';asm=subprocess.check_output([tc+'objdump','-d',str(elf)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  assert not subprocess.check_output([tc+'nm','-u',str(elf)],text=True).strip()
  syms={line.split()[-1]:int(line.split()[0],16) for line in subprocess.check_output([tc+'nm',str(elf)],text=True).splitlines() if len(line.split())==3}
  entry=syms['res_service'];assert syms['stext']==entry+8 and syms['_end']<0x88000000 and entry>0x8493a000
  raw=a.output/('kernel-'+lane+'.raw');subprocess.run([tc+'objcopy','-O','binary',str(elf),str(raw)],check=True);payload=raw.read_bytes();assert len(payload)<0x1000000
  values=[0x27051956,0,EPOCH,len(payload),0x8493a000,entry,zlib.crc32(payload)&0xffffffff,5,0x13,2,0,b'OpenMitraStar7.3 RADIOETH RAM'.ljust(32,b'\0')];values[1]=zlib.crc32(struct.pack('>7I4B32s',*values))&0xffffffff
  image=struct.pack('>7I4B32s',*values)+template[64:8192]+payload;path=a.output/('radioeth73-'+lane+'.ras.bin');path.write_bytes(image)
  lanes.append({'lane':lane,'kernel_sha256':sha(elf),'kernel_bytes':elf.stat().st_size,'image_sha256':sha(path),'image_bytes':len(image),'image_crc32':f'{zlib.crc32(image)&0xffffffff:08x}','raw_sha256':sha(raw),'payload_bytes':len(payload),'load':'0x8493a000','entry':hex(entry),'end':hex(syms['_end']),'config_sha256':sha(out/'.config'),'dtb_sha256':sha(out/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb')})
 for key in ['kernel_sha256','image_sha256','raw_sha256','config_sha256','dtb_sha256']:assert lanes[0][key]==lanes[1][key],key
 report={'schema':'openmitrastar.radioeth73-secure-ram/v2','status':'PASS_PAIRED_RAM_BUILD_PHYSICAL_UNRUN','hardware_accessed':False,'private':True,'flash_writes':0,'bootenv_writes':0,'flash_go_no_go':'NO_GO_RAM_DIAGNOSTIC_NOT_COMPLETE_PRODUCT','userland_non_sensitive':records,'dynamic_dependency_closure':needs,'lanes':lanes,'tls_certificate_sha256':sha(root/'etc/lyoko/tls/server.pem'),'ethernet_module_sha256':sha(root/'qtn-topaz-emac-eth73.ko'),'init_sha256':sha(root/'init'),'network_listeners':'HTTPS443 and modern SSH22 on explicit command only','limits':['Physical boot/userland/Ethernet/Wi-Fi/TLS/SSH unrun.','Complete persistent product with5GHz/Doom/recovery still required.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'image_bytes':lanes[0]['image_bytes'],'image_sha256':lanes[0]['image_sha256'],'entry':lanes[0]['entry'],'physical':'UNRUN','flash':'NO_GO_RAM_ONLY'}))
if __name__=='__main__':main()
