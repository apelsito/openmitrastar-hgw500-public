"""Pair-build the accepted RAM fixes without touching hardware or historical inputs.

All outputs contain per-unit keys: keep the output directory private and local.
This is RAM ONLY. Neither flash fit nor 5 GHz acceptance is implied.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,struct,subprocess,time,zlib

HERE=Path(__file__).resolve().parent
WORKSPACE=Path('/workspace/user-home/Desktop/MitraStar')
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
EPOCH=1792365298
PARENT_SHA='9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e'
UPDATES=[
 ('uhttpd73-wasm-mime-v1/a/uhttpd','usr/sbin/uhttpd','43a0fea8072cfd725ae5803bc7fc4bfd94bb734d8a321b8490945d9563c62d1c'),
 ('dropbear73-pie-qualified-v1/dropbearmulti-a','usr/sbin/dropbearmulti','23026d9cabd53cab1d9b7c5a78ef5c5be0e6842b7a81a1696af9949bf5974da0'),
]
PRIVATE=('server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow')
API=('status','capabilities','storage','network','firmware','session','hardware-led-test','frontend','ssh','clients','privacy','packages','hardware','diagnostics')

def sha(p):
 with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def require(condition,message):
 if not condition:raise RuntimeError(message)
def run(command,log,env,timeout=1800):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as stream:subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=timeout)
def output(command):return subprocess.check_output(command,text=True,stderr=subprocess.DEVNULL)
def emit(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def safe_record(p,root):
 return {'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
def elf_files(root):
 for p in sorted(root.rglob('*')):
  if p.is_file() and not p.is_symlink():
   with p.open('rb') as stream:
    if stream.read(4)==b'\x7fELF':yield p
def no_forbidden(tc,p):
 require(not re.search(r'\t(?:swape|llock|scond)(?:\t| )',output([tc+'objdump','-d',str(p)])), 'Forbidden ARC instruction in '+p.name)
def normalize_times(root):
 for p in sorted(root.rglob('*'),reverse=True):os.utime(p,(EPOCH,EPOCH),follow_symlinks=False)
 os.utime(root,(EPOCH,EPOCH))
def write_cpio_list(root,path):
 lines=[]
 for p in sorted(root.rglob('*')):
  name='/'+p.relative_to(root).as_posix()
  if p.is_symlink():lines.append('slink '+name+' '+str(p.readlink())+' 777 0 0')
  elif p.is_dir():lines.append('dir '+name+' '+format(p.stat().st_mode&0o777,'o')+' 0 0')
  else:lines.append('file '+name+' '+str(p)+' '+format(p.stat().st_mode&0o777,'o')+' 0 0')
 for name,major,minor,mode in [('console',5,1,'600'),('ttyS0',4,64,'600'),('null',1,3,'666'),('zero',1,5,'666'),('random',1,8,'444'),('urandom',1,9,'444'),('ptmx',5,2,'666')]:
  lines.append(f'nod /dev/{name} {mode} 0 0 c {major} {minor}')
 path.write_text('\n'.join(lines)+'\n');os.utime(path,(EPOCH,EPOCH))

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 require(not args.output.exists(),'Immutable output already exists')
 os.umask(0o077);out=args.output;out.mkdir(mode=0o700)
 context=BASE/'radioeth73-events-ram-v2'
 root_parent=BASE/'radioeth73-secure-ram-v1/initramfs/root'
 parent=BASE/'radioeth73-events-artifact-v1/radioeth73-events-a.ras.bin'
 require(sha(parent)==PARENT_SHA,'Parent image pin mismatch')
 receipt=json.loads((parent.parent/'result.json').read_text())
 require(sha(context/'a/vmlinux')==sha(context/'b/vmlinux')==receipt['lanes'][0]['kernel_sha256'],'Parent kernel pair mismatch')
 tc=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
 require(sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263','Compiler pin mismatch')
 env=os.environ|{'SOURCE_DATE_EPOCH':str(EPOCH),'KBUILD_BUILD_TIMESTAMP':'@'+str(EPOCH),'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73','KBUILD_BUILD_VERSION':'1'}
 emit(out/'status.json',{'status':'BUILDING_OFFLINE','hardware_accessed':False,'flash':'NO_GO_RAM_ONLY','parent_image_sha256':PARENT_SHA})
 source=out/'source'
 run(['cp','-a','--reflink=auto',str(context/'source'),str(source)],out/'copy-source.log',env)
 ir=out/'initramfs';ir.mkdir();root=ir/'root'
 shutil.copytree(root_parent,root,symlinks=True)
 (root/'root').chmod(0o700);(root/'root/.ssh').chmod(0o700)
 for rel in ['run/openmitrastar/secrets','run/openmitrastar/web/sessions']:(root/rel).chmod(0o700)
 source_rows=[]
 for relative,dest,pin in UPDATES:
  src=BASE/relative
  require(sha(src)==pin,'Qualified service pin mismatch: '+dest)
  shutil.copyfile(src,root/dest);(root/dest).chmod(0o755)
  source_rows.append({'source':relative,'target':dest,'sha256':pin})
 # Use the already qualified exact eleven game files, not a new game build.
 assets=json.loads((WORKSPACE/'outputs/doom/linux73-https-assets-v31/manifest.json').read_text())['records']
 game=root/'www/Doom';require(not game.exists(),'Unexpected parent game directory');game.mkdir(mode=0o755)
 for row in assets:
  if not row['target'].startswith('/www/Doom/'):continue
  src=Path('/mnt/c')/row['local'][3:].replace('\\','/')
  require(sha(src)==row['sha256'] and src.stat().st_size==row['bytes'],'Game input pin mismatch')
  dst=game/row['name'];shutil.copyfile(src,dst);dst.chmod(0o644)
 require(len(list(game.iterdir()))==11,'Incomplete preserved game package')
 # Same credential value; Windows line endings are not part of the credential.
 credential=root/'run/openmitrastar/secrets/web.password.sha256'
 original=credential.read_bytes();value=original.strip()
 require(re.fullmatch(rb'[0-9a-fA-F]{64}',value) is not None,'Credential shape rejected')
 credential.write_bytes(value+b'\n');credential.chmod(0o600)
 require(credential.read_bytes().strip()==original.strip(),'Credential value changed')
 (root/'bin/id').symlink_to('busybox')
 (root/'etc/om73-web.conf').write_text(''.join('*/api/v1/'+name+':/bin/sh\n' for name in API))
 (root/'etc/om73-web.conf').chmod(0o644)
 for name in API:
  path=root/'www/api/v1'/name
  require(path.is_file() and path.read_bytes().splitlines()[0] in (b'#!/bin/sh',b'#!/bin/ash'),'API script contract changed: '+name)
  require(path.stat().st_mode&0o111,'API script is not executable: '+name)
 for p in root.rglob('*'):
  if p.is_file() and not p.is_symlink() and any(k in p.relative_to(root).as_posix() for k in PRIVATE):
   require(p.stat().st_mode&0o777==0o600,'Private file permission is not 0600')
 # Record candidate identity independently of unchanged module release string.
 (root/'etc/openmitrastar/release').write_text('OPENMITRASTAR_PRODUCT_VERSION=lyoko-linux73-radioeth-integrated-r2\nOPENMITRASTAR_BUILD_ID=radioeth73-integrated-r2\n')
 # A freestanding PID1 retaining the parent radio and Ethernet loading contract.
 old_init=WORKSPACE/'work/kernel-port/linux-7.3-radioeth-ram-v1/init-secure-v2.c'
 text=old_init.read_text()
 require(sha(old_init)=='eb5bf58ec5a18fd0b3ecabdc3ee2df3c6842d5e0608dd119091b0f46fdfeb3b1','Parent init pin mismatch')
 old='"/usr/sbin/dropbearmulti","dropbear","-E","-s",'
 require(text.count(old)==1,'Parent SSH launcher drift')
 text=text.replace(old,'"/usr/sbin/dropbearmulti","dropbear","-j","-k",')
 text=text.replace('"/usr/sbin/uhttpd","-s","0.0.0.0:443","-h","/www",','"/usr/sbin/uhttpd","-c","/etc/om73-web.conf","-s","0.0.0.0:443","-h","/www",')
 text=text.replace('OPENMITRASTAR_RADIOETH73_RAM_V1','OPENMITRASTAR_RADIOETH73_INTEGRATED_R2')
 require('"-E","-s"' not in text,'Unsupported Dropbear options retained')
 init_source=out/'init-integrated-r2.c';init_source.write_text(text)
 # Preserve radio module parameters byte for byte.
 radio=lambda s:s.split('static const struct module_input radio_modules[] = {',1)[1].split('};',1)[0]
 require(radio(text)==radio(old_init.read_text()),'Radio parameter contract changed')
 run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Werror','-Wl,-e,_start','-Wl,--build-id=none','-o',str(root/'init'),str(init_source)],out/'init-build.log',env)
 (root/'init').chmod(0o755)
 # Strong imports must resolve against the packaged shared libraries.
 files=list(elf_files(root));exports=set();needs={}
 for p in files:
  for line in output([tc+'nm','-D','--defined-only',str(p)]).splitlines():
   if line.split():exports.add(line.split()[-1].split('@')[0])
 for p in files:
  no_forbidden(tc,p)
  if p.suffix=='.ko' or p.name=='init':continue
  imports={line.split()[-1].split('@')[0] for line in output([tc+'nm','-D','--undefined-only',str(p)]).splitlines() if line.split() and line.split()[0]=='U'}
  require(not imports-exports,'Packaged ELF has unresolved strong imports: '+p.name)
  libraries=re.findall(r'\(NEEDED\).*\[([^]]+)\]',output([tc+'readelf','-d',str(p)]))
  require(all((root/'lib'/n).is_file() for n in libraries),'Packaged shared library is absent')
  needs[p.relative_to(root).as_posix()]=libraries
 normalize_times(root);listing=ir/'list';write_cpio_list(root,listing)
 lanes=[];configs=[];kernel_modules=[]
 for lane in ['a','b']:
  build=out/lane;run(['cp','-a','--reflink=auto',str(context/lane),str(build)],out/('copy-context-'+lane+'.log'),env)
  config=(build/'.config').read_text()
  config=re.sub(r'CONFIG_INITRAMFS_SOURCE="[^"]*"','CONFIG_INITRAMFS_SOURCE="'+str(listing)+'"',config)
  config=config.replace('# CONFIG_BINFMT_SCRIPT is not set','CONFIG_BINFMT_SCRIPT=y')
  (build/'.config').write_text(config)
  make=['make','-C',str(source),'O='+str(build),'ARCH=arc','CROSS_COMPILE='+tc]
  run(make+['olddefconfig'],out/('config-'+lane+'.log'),env)
  final=(build/'.config').read_text()
  require('CONFIG_BINFMT_SCRIPT=y\n' in final,'Kernel script support absent')
  before={l.split('=',1)[0]:l for l in (context/lane/'.config').read_text().splitlines() if l.startswith('CONFIG_') or l.startswith('# CONFIG_')}
  after={l.split('=',1)[0]:l for l in final.splitlines() if l.startswith('CONFIG_') or l.startswith('# CONFIG_')}
  differences=[{'before':before.get(k),'after':after.get(k)} for k in sorted(before.keys()|after.keys()) if before.get(k)!=after.get(k)]
  require(all(any(token in str(row) for token in ['CONFIG_INITRAMFS_SOURCE','CONFIG_BINFMT_SCRIPT']) for row in differences),'Unexpected kernel config change')
  configs.append(differences)
  run(make+['KCFLAGS=-ffile-prefix-map='+str(build)+'=/radio73-build','-j6','vmlinux','dtbs','modules'],out/('kernel-'+lane+'.log'),env)
  native={p.name:sha(p) for p in build.rglob('*.ko')}
  parent_native={p.name:sha(p) for p in (context/lane).rglob('*.ko')}
  require(native==parent_native,'In-tree radio module content changed')
  require(len(native)==19,'In-tree module closure count changed')
  for p in (root/'modules').glob('*.ko'):require(native.get(p.name)==sha(p),'Packaged radio module mismatch')
  driver=out/('emac-'+lane)
  shutil.copytree(WORKSPACE/'work/kernel-port/linux-7.3-radioeth-ram-v1/candidate/driver',driver)
  # Preserve the parent's diagnostic __FILE__ string in dma-mapping.h.
  parent_source=BASE/'radioeth73-secure-ram-v1/source'
  module_flags='-ffile-prefix-map='+str(driver)+'=/radioeth73-module -ffile-prefix-map='+str(source)+'='+str(parent_source)
  run(make+['M='+str(driver),'KCFLAGS='+module_flags,'-j6','modules'],out/('emac-'+lane+'.log'),env)
  ko=driver/'qtn-topaz-emac-eth73.ko'
  require(sha(ko)==sha(root/'qtn-topaz-emac-eth73.ko'),'Ethernet module changed under new context')
  symbols={l.split()[1] for l in (build/'Module.symvers').read_text().splitlines()}
  for p in list((root/'modules').glob('*.ko'))+[ko]:
   imports={l.split()[-1] for l in output([tc+'nm','-u',str(p)]).splitlines()}
   require(not imports-symbols,'Module imports are unresolved: '+p.name)
  kernel_modules.append(native)
  elf=build/'vmlinux';no_forbidden(tc,elf)
  require(not output([tc+'nm','-u',str(elf)]).strip(),'Kernel has unresolved imports')
  syms={l.split()[-1]:int(l.split()[0],16) for l in output([tc+'nm',str(elf)]).splitlines() if len(l.split())==3}
  entry=syms['res_service'];require(syms['stext']==entry+8 and 0x8493a000<entry<syms['_end']<0x88000000,'Boot address contract failed')
  dtb=build/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb'
  require(sha(dtb)==receipt['lanes'][0]['dtb_sha256'],'Per-unit DT changed')
  raw=out/('kernel-'+lane+'.raw');subprocess.run([tc+'objcopy','-O','binary',str(elf),str(raw)],check=True)
  payload=raw.read_bytes();require(len(payload)<0x1000000,'RAM payload bound exceeded')
  values=[0x27051956,0,EPOCH,len(payload),0x8493a000,entry,zlib.crc32(payload)&0xffffffff,5,0x13,2,0,b'OpenMitraStar7.3 RADIOETH RAM'.ljust(32,b'\0')]
  values[1]=zlib.crc32(struct.pack('>7I4B32s',*values))&0xffffffff
  image=struct.pack('>7I4B32s',*values)+parent.read_bytes()[64:8192]+payload
  path=out/('radioeth73-integrated-r2-'+lane+'-RAM-ONLY.ras.bin');path.write_bytes(image)
  lanes.append({'lane':lane,'kernel_sha256':sha(elf),'image_sha256':sha(path),'image_bytes':len(image),'image_crc32':f'{zlib.crc32(image)&0xffffffff:08x}','raw_sha256':sha(raw),'payload_bytes':len(payload),'load':'0x8493a000','entry':hex(entry),'end':hex(syms['_end']),'config_sha256':sha(build/'.config'),'dtb_sha256':sha(dtb)})
 for key in ['kernel_sha256','image_sha256','raw_sha256','config_sha256','dtb_sha256']:
  require(lanes[0][key]==lanes[1][key],'Pair differs: '+key)
 inventory=[safe_record(p,root) for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink() and not any(k in p.relative_to(root).as_posix() for k in PRIVATE)]
 report={'schema':'openmitrastar.radioeth73-integrated-r2/v1','status':'PASS_PAIRED_RAM_INTEGRATION_PHYSICAL_UNRUN','hardware_accessed':False,'flash_writes':0,'bootenv_writes':0,'flash_go_no_go':'NO_GO_RAM_ONLY_5GHZ_PERSISTENCE_RECOVERY_PENDING','parent_image_sha256':PARENT_SHA,'changes':['Qualified Dropbear PIE and supported launcher flags','Qualified uhttpd WASM MIME and explicit API interpreters','Same web credential normalized to LF; BusyBox id symlink','BINFMT_SCRIPT enabled; all other kernel configuration unchanged','Eleven exact original Doom assets retained, no game optimization'],'unchanged':['19 in-tree module hashes and Ethernet module','DT hash, radio parameters, load/entry contract','Explicit UART service/radio activation; no automatic 5GHz activation','Parent reset implementation'],'source_inputs':source_rows,'parent_init_sha256':sha(old_init),'init_source_sha256':sha(init_source),'builder_sha256':sha(Path(__file__)),'config_differences':configs,'dynamic_dependency_closure':needs,'module_hashes':kernel_modules[0],'userland_non_sensitive':inventory,'game_files':11,'game_raw_bytes':sum(p.stat().st_size for p in game.iterdir()),'lanes':lanes,'limits':['New image has not booted physically. Parent physical acceptance does not transfer.','RAM only; exceeds prefix and does not contain 5GHz product services or accepted recovery.','No browser/game source rebuild or optimization performed.']}
 emit(out/'result.json',report);emit(out/'status.json',{'status':report['status'],'flash':'NO_GO_RAM_ONLY','lanes':lanes})
 print(json.dumps({'status':report['status'],'lanes':lanes,'game_raw_bytes':report['game_raw_bytes']},indent=2))

if __name__=='__main__':main()
