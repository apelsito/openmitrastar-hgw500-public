"""Package current secure userland and radio/Ethernet into paired RAM images.

Private per-unit DT, host key, test PSK and TLS key stay local. No device access.
This diagnostic RAM image is not the persistent full-product/Doom release.
"""
import argparse,gzip,hashlib,json,os,re,shutil,struct,subprocess,zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EPOCH=1792365298

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run(command,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['context','sysroot','userland-root','toolchain','template','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 assert sha(a.context/'a/vmlinux')==sha(a.context/'b/vmlinux')=='b13f22156a871719b7a713a8fef614b67f37687596995d919940f48e4b252cd8'
 env=os.environ|{'SOURCE_DATE_EPOCH':str(EPOCH),'KBUILD_BUILD_TIMESTAMP':'@'+str(EPOCH),'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73','KBUILD_BUILD_VERSION':'1'}
 source=a.output/'source';run(['cp','-a','--reflink=auto',str(a.context/'source'),str(source)],a.output/'copy-source.log',env)
 ir=a.output/'initramfs';ir.mkdir();root=ir/'root';root.mkdir()
 directories=['dev','dev/pts','proc','sys','tmp','run','root','root/.ssh','etc','etc/dropbear','etc/lyoko','etc/lyoko/tls','lib','lib/firmware','lib/firmware/rtlwifi','modules','bin','usr','usr/bin','usr/sbin','www','run/openmitrastar','run/openmitrastar/secrets','run/openmitrastar/web','run/openmitrastar/web/sessions','run/hostapd']
 for name in directories:(root/name).mkdir(parents=True,exist_ok=True)
 module_records=[]
 # Exact dependency closure from the newly paired kernel context.
 for file in sorted((a.context/'a').rglob('*.ko')):
  assert sha(file)==sha(a.context/'b'/file.relative_to(a.context/'a'))
  target=root/'modules'/file.name;assert not target.exists();shutil.copyfile(file,target)
  module_records.append({'name':file.name,'bytes':file.stat().st_size,'sha256':sha(file)})
 # Full Ethernet module compiled against this final context, twice identical.
 exports={l.split()[1] for l in (a.context/'a/Module.symvers').read_text().splitlines()}
 modules=[]
 for lane in ['a','b']:
  module=a.output/('emac-'+lane);shutil.copytree(HERE/'candidate/driver',module)
  command=['make','-C',str(source),'O='+str(a.context/lane),'ARCH=arc','CROSS_COMPILE='+tc,'M='+str(module),'KCFLAGS=-ffile-prefix-map='+str(module)+'=/radioeth73-module','-j6','modules']
  run(command,a.output/('module-'+lane+'.log'),env)
  ko=module/'qtn-topaz-emac-eth73.ko';imports={l.split()[-1] for l in subprocess.check_output([tc+'nm','-u',str(ko)],text=True).splitlines()};assert not imports-exports
  modules.append(ko)
 assert sha(modules[0])==sha(modules[1]);shutil.copyfile(modules[0],root/'qtn-topaz-emac-eth73.ko')
 # Current programs; no cleartext network services included in launcher.
 inputs={
  'bin/busybox':a.userland_root/'busybox2026-resume-qualified-v4/busybox',
  'usr/sbin/dropbearmulti':a.userland_root/'dropbear2026-arc750-v1/dropbearmulti',
  'usr/sbin/hostapd':a.userland_root/'hostapd2026-qualified-v3/hostapd',
  'usr/sbin/hostapd_cli':a.userland_root/'hostapd2026-qualified-v3/hostapd_cli',
  'usr/sbin/iw':a.userland_root/'iw6_17-arc750-v1/iw-6.17/iw',
  'usr/sbin/uhttpd':a.userland_root/'modern-web-arc750-v1/install/bin/uhttpd',
  'usr/bin/jshn':a.userland_root/'modern-web-arc750-v1/install/bin/jshn',
  'lib/firmware/rtlwifi/rtl8192eefw.bin':a.userland_root/'radio73-runtime-assets-v1/lib/firmware/rtlwifi/rtl8192eefw.bin',
  'lib/firmware/regulatory.db':a.userland_root/'radio73-signed-regdb-v1/regulatory.db',
  'lib/firmware/regulatory.db.p7s':a.userland_root/'radio73-signed-regdb-v1/regulatory.db.p7s',
 }
 assert sha(inputs['bin/busybox'])=='d4969ee5b551c650bd18686afb9f4edc9357e4526543a7de0d6400e5f40cdcc5'
 for name,file in inputs.items():shutil.copyfile(file,root/name);(root/name).chmod(0o755 if name.startswith(('bin/','usr/')) else 0o644)
 for file in (a.sysroot/'lib').iterdir():
  target=root/'lib'/file.name
  if file.is_symlink():target.symlink_to(file.readlink())
  elif file.is_file():shutil.copyfile(file,target);target.chmod(0o755)
 prefix=a.userland_root/'modern-web-arc750-v1/install/lib'
 for file in prefix.iterdir():
  if '.so' not in file.name or file.name.startswith('libwolfssl'):continue
  target=root/'lib'/file.name
  if file.is_symlink():target.symlink_to(file.readlink())
  else:shutil.copyfile(file,target);target.chmod(0o755)
 wolf=a.userland_root/'hostapd2026-qualified-v3/libwolfssl.so.46.0.0';shutil.copyfile(wolf,root/'lib/libwolfssl.so.46.0.0')
 (root/'lib/libwolfssl.so.46').symlink_to('libwolfssl.so.46.0.0');(root/'lib/libwolfssl.so').symlink_to('libwolfssl.so.46.0.0')
 # Existing product web presentation and original own CGI; test-only RAM root.
 reference=a.userland_root/'product-web-reference-v1'
 for directory in ['www','usr/share/openmitrastar/web','etc/lyoko']:
  shutil.copytree(reference/directory,root/directory,dirs_exist_ok=True)
 for name in ['usr/libexec/openmitrastar/om-oem-cgi','usr/libexec/openmitrastar/om-api-v1']:
  target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(reference/name,target);target.chmod(0o755)
 for f in (root/'www').rglob('*'):
  if f.is_file() and (f.suffix=='.cgi' or '/api/v1/' in f.as_posix()):f.chmod(0o755)
 # Private identity provisioning; never print bytes or store in public receipt.
 device=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary')
 shutil.copyfile(device/'dropbear_ed25519_host_key',root/'etc/dropbear/dropbear_ed25519_host_key');(root/'etc/dropbear/dropbear_ed25519_host_key').chmod(0o600)
 (root/'root/.ssh/authorized_keys').write_bytes(Path('/workspace/user-home/.ssh/id_ed25519.pub').read_bytes());(root/'root/.ssh/authorized_keys').chmod(0o600)
 for name in ['root','root/.ssh','run/openmitrastar/secrets','run/openmitrastar/web/sessions']:(root/name).chmod(0o700)
 (root/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\n');(root/'etc/shadow').write_text('root:*:19000:0:99999:7:::\n');(root/'etc/shadow').chmod(0o600)
 (root/'etc/group').write_text('root:x:0:\n');(root/'etc/hosts').write_text('127.0.0.1 localhost\n')
 (root/'etc/openmitrastar').mkdir();(root/'etc/openmitrastar/release').write_text('OPENMITRASTAR_PRODUCT_VERSION=lyoko-linux73-radioeth-ram-v1\nOPENMITRASTAR_BUILD_ID=radioeth73-ram-v1\n')
 webhash=(device/'web_password.sha256').read_bytes();assert re.fullmatch(rb'[0-9a-fA-F]{64}\s*',webhash)
 (root/'run/openmitrastar/secrets/web.password.sha256').write_bytes(webhash);(root/'run/openmitrastar/secrets/web.password.sha256').chmod(0o600)
 psk=(ROOT/'work/mission-state/.openmitrastar-lab.psk').read_text().strip();assert 8<=len(psk)<=63 and '\n' not in psk and '\r' not in psk
 ap=root/'run/hostapd-test.conf';ap.write_text('interface=wlan0\ndriver=nl80211\nctrl_interface=/run/hostapd\nssid=LYOKO-73-TEST\ncountry_code=ES\nieee80211d=1\nhw_mode=g\nchannel=1\nieee80211n=1\nwmm_enabled=1\nwpa=2\nwpa_key_mgmt=WPA-PSK\nrsn_pairwise=CCMP\nwpa_passphrase='+psk+'\n');ap.chmod(0o600)
 # Public test certificate and private key scoped only to this RAM artifact.
 key=root/'etc/lyoko/tls/server.key';cert=root/'etc/lyoko/tls/server.pem'
 run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-sha256','-nodes','-days','30','-subj','/CN=om-hgw500.local','-addext','subjectAltName=DNS:om-hgw500.local,IP:192.168.1.90,IP:192.168.1.91,IP:192.168.73.1','-keyout',str(key),'-out',str(cert)],a.output/'certificate-generation.log',env);key.chmod(0o600)
 # Finite HTTPS integrity payload, no UDP echo listener.
 (root/'www/__traffic.bin').write_bytes(bytes(range(256))*256)
 for name in ['sh','ash','cat','ls','mkdir','chmod','rm','mv','cp','sed','awk','head','tail','cut','tr','wc','grep','date','sleep','sha256sum','test','mount','umount','ip','ifconfig','route','netstat','ps','kill','dd','readlink','ln','uname']:
  (root/'bin'/name).symlink_to('busybox')
 init=ir/'init';run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Werror','-Wl,-e,_start','-Wl,--build-id=none','-o',str(init),str(HERE/'init-secure-v2.c')],a.output/'init-build.log',env)
 shutil.copyfile(init,root/'init');(root/'init').chmod(0o755)
 # Resolve all strong dynamic imports against packaged ELF providers.
 elf_files=[f for f in root.rglob('*') if f.is_file() and not f.is_symlink() and f.read_bytes().startswith(b'\x7fELF')]
 dynamic_exports=set()
 for file in elf_files:
  for l in subprocess.check_output([tc+'nm','-D','--defined-only',str(file)],text=True,stderr=subprocess.DEVNULL).splitlines():
   if l.split():dynamic_exports.add(l.split()[-1].split('@')[0])
 for file in elf_files:
  asm=subprocess.check_output([tc+'objdump','-d',str(file)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),file
  if file.suffix!='.ko' and file.name!='init':
   imports={l.split()[-1].split('@')[0] for l in subprocess.check_output([tc+'nm','-D','--undefined-only',str(file)],text=True,stderr=subprocess.DEVNULL).splitlines() if l.split() and l.split()[0]=='U'}
   assert not imports-dynamic_exports,(file,imports-dynamic_exports)
 records=[];lines=[]
 for file in sorted(root.rglob('*')):
  name='/'+file.relative_to(root).as_posix();mode=file.stat().st_mode&0o777
  if file.is_symlink():lines.append('slink '+name+' '+str(file.readlink())+' 777 0 0')
  elif file.is_dir():lines.append('dir '+name+' '+format(mode,'o')+' 0 0')
  else:lines.append('file '+name+' '+str(file)+' '+format(mode,'o')+' 0 0')
  if file.is_file() and not file.is_symlink() and not any(k in name for k in ['server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow']):records.append({'path':name,'bytes':file.stat().st_size,'sha256':sha(file)})
 for name,major,minor,mode in [('console',5,1,'600'),('ttyS0',4,64,'600'),('null',1,3,'666'),('zero',1,5,'666'),('random',1,8,'444'),('urandom',1,9,'444'),('ptmx',5,2,'666')]:lines.append('nod /dev/'+name+' '+mode+' 0 0 c '+str(major)+' '+str(minor))
 listing=ir/'list';listing.write_text('\n'.join(lines)+'\n');lanes=[]
 template=a.template.read_bytes();assert sha(a.template)=='84e4047246c3ae0a13435e9a113f08dbf30f3d0267543e58d56995189a773573'
 for lane in ['a','b']:
  out=a.output/lane;run(['cp','-a','--reflink=auto',str(a.context/lane),str(out)],a.output/('copy-build-'+lane+'.log'),env)
  config=(out/'.config').read_text();config=re.sub(r'CONFIG_INITRAMFS_SOURCE="[^"]*"','CONFIG_INITRAMFS_SOURCE="'+str(listing)+'"',config);(out/'.config').write_text(config)
  make=['make','-C',str(source),'O='+str(out),'ARCH=arc','CROSS_COMPILE='+tc]
  run(make+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
  run(make+['KCFLAGS=-ffile-prefix-map='+str(out)+'=/radio73-build','-j6','vmlinux','dtbs'],a.output/('build-'+lane+'.log'),env)
  elf=out/'vmlinux';asm=subprocess.check_output([tc+'objdump','-d',str(elf)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  syms={l.split()[-1]:int(l.split()[0],16) for l in subprocess.check_output([tc+'nm',str(elf)],text=True).splitlines() if len(l.split())==3}
  entry=syms['res_service'];assert syms['stext']==entry+8 and syms['_end']<0x88000000 and entry>0x8493a000
  raw=a.output/('kernel-'+lane+'.raw');subprocess.run([tc+'objcopy','-O','binary',str(elf),str(raw)],check=True);payload=raw.read_bytes();assert len(payload)<0x1000000
  values=[0x27051956,0,EPOCH,len(payload),0x8493a000,entry,zlib.crc32(payload)&0xffffffff,5,0x13,2,0,b'OpenMitraStar7.3 RADIOETH RAM'.ljust(32,b'\0')];values[1]=zlib.crc32(struct.pack('>7I4B32s',*values))&0xffffffff
  image=struct.pack('>7I4B32s',*values)+template[64:8192]+payload;path=a.output/('radioeth73-'+lane+'.ras.bin');path.write_bytes(image)
  lanes.append({'lane':lane,'kernel_sha256':sha(elf),'kernel_bytes':elf.stat().st_size,'image_sha256':sha(path),'image_bytes':len(image),'image_crc32':f'{zlib.crc32(image)&0xffffffff:08x}','raw_sha256':sha(raw),'payload_bytes':len(payload),'load':'0x8493a000','entry':hex(entry),'end':hex(syms['_end']),'config_sha256':sha(out/'.config'),'dtb_sha256':sha(out/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb')})
 for k in ['kernel_sha256','image_sha256','raw_sha256','config_sha256','dtb_sha256']:assert lanes[0][k]==lanes[1][k],k
 report={'schema':'openmitrastar.radioeth73-secure-ram/v1','status':'PASS_PAIRED_RAM_BUILD_PHYSICAL_UNRUN','hardware_accessed':False,'private':True,'flash_writes':0,'bootenv_writes':0,'flash_go_no_go':'NO_GO_RAM_DIAGNOSTIC_NOT_COMPLETE_PRODUCT','modules':module_records,'ethernet_module_sha256':sha(modules[0]),'userland_non_sensitive':records,'lanes':lanes,'tls_certificate_sha256':sha(cert),'radio_loading':'EXPLICIT_UART_ONLY','ap_loading':'EXPLICIT_UART_ONLY','network_listeners':'HTTPS443 and modern SSH22 on explicit command only; no HTTP/TFTP/Telnet/UDP echo','limits':['Physical boot/userland/Ethernet/Wi-Fi/TLS/SSH unrun.','This is RAM diagnostic; full persistent product with5GHz/Doom and recovery still required.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'image_bytes':lanes[0]['image_bytes'],'image_sha256':lanes[0]['image_sha256'],'entry':lanes[0]['entry'],'physical':'UNRUN','flash':'NO_GO_RAM_ONLY'}))

if __name__=='__main__':main()
