"""Build a pinned persistent2g/Doom candidate, flatCPIO and BootbaseLZMA.

Uses the accepted2g kernel/module ABI. Flash contains full initramfs, reloaded
into RAM on every boot. Configuration changes remain volatile in this first
candidate; preserved store/OEM/protected slots never participate in packaging.
No UART, reboot, flash, network or automatic hardware operations from builder.
"""
from pathlib import Path
import argparse,dataclasses,hashlib,importlib.util,json,lzma,os,re,shutil,struct,subprocess,zlib
HERE=Path(__file__).resolve().parent
WORK=Path('/workspace/user-home/Desktop/MitraStar')
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
R2=BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z'
ROOT_SEED=BASE/'radio73-2g-doom-fit-v1/root'
EPOCH=1792365298
PRIVATE=('server.key','hostapd-test.conf','web.password','dropbear_ed25519_host_key','authorized_keys','etc/shadow')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def output(cmd):return subprocess.check_output(cmd,text=True,stderr=subprocess.DEVNULL)
def run(cmd,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def getconfig(text):
 rows={}
 for line in text.splitlines():
  if line.startswith('CONFIG_'):key,value=line.split('=',1);rows[key]=value
  elif line.startswith('# CONFIG_') and line.endswith(' is not set'):rows[line[2:-11]]='n'
 return rows
def setconfig(text,key,value):
 pattern=r'(?m)^(?:'+re.escape(key)+r'=.*|# '+re.escape(key)+r' is not set)$'
 line=key+'='+value if value!='n' else '# '+key+' is not set'
 return re.sub(pattern,line,text) if re.search(pattern,text) else text+'\n'+line+'\n'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 require(not a.output.exists(),'Immutable output exists');os.umask(0o077);a.output.mkdir(mode=0o700)
 parent=json.loads((R2/'result.json').read_text());require(parent['status']=='PASS_PAIRED_RAM_INTEGRATION_PHYSICAL_UNRUN','R2 pair absent')
 require(sha(R2/'a/vmlinux')==sha(R2/'b/vmlinux')==parent['lanes'][0]['kernel_sha256'],'R2 pair drift')
 tc=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
 require(sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263','Compiler identity drift')
 env=os.environ|{'SOURCE_DATE_EPOCH':str(EPOCH),'KBUILD_BUILD_TIMESTAMP':'@'+str(EPOCH),'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73','KBUILD_BUILD_VERSION':'1'}
 root=a.output/'initramfs/root';root.parent.mkdir();shutil.copytree(ROOT_SEED,root,symlinks=True)
 (root/'etc/openmitrastar/release').write_text('OPENMITRASTAR_PRODUCT_VERSION=lyoko-linux73-2g-doom-flash-r1\nOPENMITRASTAR_BUILD_ID=radio73-2g-doom-autostart-flat-r1\n')
 (root/'etc/udhcpd-wlan.conf').write_text('start 192.168.73.20\nend 192.168.73.40\ninterface wlan0\nmax_leases 21\nlease_file /run/udhcpd.leases\npidfile /run/udhcpd.pid\noption subnet 255.255.255.0\noption lease 300\n')
 (root/'etc/udhcpd-wlan.conf').chmod(0o644)
 (root/'www/__traffic.cgi').write_text('#!/bin/sh\ncase "$CONTENT_LENGTH" in 65536) ;; *) printf "Status: 413 Payload Too Large\\r\\nContent-Type: text/plain\\r\\n\\r\\nrejected\\n"; exit 0;; esac\ndigest=$(/bin/busybox head -c 65536 | /bin/busybox sha256sum)\nprintf "Content-Type: text/plain\\r\\nCache-Control: no-store\\r\\n\\r\\n%s\\n" "$digest"\n')
 (root/'www/__traffic.cgi').chmod(0o755)
 # Exact2gparams and loading order remain parent code; only boot activation
 # and current supported service flags/config are added to qualified PID1.
 text=(R2/'init-integrated-r2.c').read_text()
 text=text.replace('OPENMITRASTAR_RADIOETH73_INTEGRATED_R2','OPENMITRASTAR_RADIOETH73_FLASH2G_R1')
 # Run daemon children foreground, owned/reaped by PID1; keep output local.
 old='const char *const args[]={"/usr/sbin/dropbearmulti","dropbear","-j","-k",'
 require(text.count(old)==1,'Qualified SSH launcher drift')
 text=text.replace(old,'const char *const args[]={"/usr/sbin/dropbearmulti","dropbear","-F","-j","-k",')
 start=text.index('static void ssh_start(void)');end=text.index('static void https_start(void)',start)
 ssh=text[start:end].replace('0};child(args,0);','0};child(args,1);')
 text=text[:start]+ssh+text[end:]
 start=text.index('static void https_start(void)');end=text.index('static void userland_test(void)',start)
 https=text[start:end].replace('"/usr/sbin/uhttpd","-c",','"/usr/sbin/uhttpd","-f","-c",').replace('0};child(args,0);','0};child(args,1);')
 text=text[:start]+https+text[end:]
 # Select a connected management port at boot; both original driver ports are
 # retained. Avoid competing subnet routes when only one cable is connected.
 autostart=r'''
static int port_carrier(unsigned which) {
 char path[]="/sys/class/net/eth0/carrier";path[18]='0'+which;
 char value=0;long fd=call5(56,AT_FDCWD,(long)path,0,0,0);
 if(fd<0)return 0;
 long got=call5(63,fd,(long)&value,1,0,0);call5(57,fd,0,0,0,0);
 return got==1&&value=='1';
}
static void autostart(void) {
 say("AUTOSTART_BEGIN\n");
 load_driver();
 if(!loaded){say("AUTOSTART_ETH_FAILURE\n");return;}
 iface(0,1);iface(1,1);
 for(unsigned i=0;i<30&&!port_carrier(0)&&!port_carrier(1);i++)pause_ms(100);
 if(port_carrier(0)){iface(1,0);say("AUTOSTART_MANAGEMENT_ETH0\n");}
 else if(port_carrier(1)){iface(0,0);say("AUTOSTART_MANAGEMENT_ETH1\n");}
 else{iface(1,0);say("AUTOSTART_MANAGEMENT_ETH0_NO_CARRIER\n");}
 ssh_start();https_start();
 load_radio();radio_country();
 if(radio_loaded==sizeof(radio_modules)/sizeof(radio_modules[0])) {
  const char *const wlan[]={"/bin/busybox","ifconfig","wlan0","192.168.73.1","netmask","255.255.255.0","up",0};
  child(wlan,0);radio_ap();
  const char *const dhcp[]={"/bin/busybox","udhcpd","-f","/etc/udhcpd-wlan.conf",0};
  child(dhcp,1);
 }
 say("AUTOSTART_END\n");
}
'''
 anchor='static volatile u32 ram[262144];';require(text.count(anchor)==1,'PID1 integration anchor drift');text=text.replace(anchor,autostart+'\n'+anchor)
 anchor='cat("/proc/sys/kernel/osrelease");say("eth73> ");'
 require(text.count(anchor)==1,'PID1 boot marker drift')
 text=text.replace(anchor,'cat("/proc/sys/kernel/osrelease");autostart();say("eth73> ");')
 # Parent radios are never replaced by diagnostic5GHz objects.
 require('om73_sram' not in text and 'qdrv' not in text,'Unexpected5gautostart')
 init=a.output/'init-autostart2g.c';init.write_text(text)
 run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Werror','-Wl,-e,_start','-Wl,--build-id=none','-o',str(root/'init'),str(init)],a.output/'init-build.log',env)
 (root/'init').chmod(0o755)
 for f in root.rglob('*'):
  if f.is_file() and not f.is_symlink() and any(k in f.relative_to(root).as_posix() for k in PRIVATE):require(f.stat().st_mode&0o777==0o600,'Private mode drift')
 spec=importlib.util.spec_from_file_location('r2',HERE/'build_integrated_r2.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 helper.normalize_times(root);listing=a.output/'initramfs/list';helper.write_cpio_list(root,listing)
 ras_parent=BASE/'radioeth73-events-artifact-v1/radioeth73-events-a.ras.bin'
 require(sha(ras_parent)=='9a2aa3766d0136b593bf476cecfcc27c53548f1b60e8f8fab1bc3644509f7e2e','Parent RAS template drift')
 # The same compression defaults as the known-good LZMA source. dict capped
 # at8MiB for bounded Bootbase decoder RAM and exact output-size header.
 sys_path=str(WORK/'tools')
 import sys;sys.path.insert(0,sys_path)
 from bootbase_contract_emulator import validate_bootbase_slot
 report={'status':'BUILDING_2G_FLASH_CANDIDATE','hardware_accessed':False,'flash_writes':0,'bootenv_writes':0,'normal_write_target':'physicalmtd4/linux_live prefixonly','preserved_store_bytes':0x1c0000,'physical_boot':'UNRUN','physical_flash':'UNRUN','lanes':[]}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 try:
  for lane in ['a','b']:
   build=a.output/lane;run(['cp','-a','--reflink=auto',str(R2/lane),str(build)],a.output/('copy-'+lane+'.log'),env)
   config=(build/'.config').read_text();config=setconfig(config,'CONFIG_INITRAMFS_SOURCE','"'+str(listing)+'"')
   config=setconfig(config,'CONFIG_INITRAMFS_COMPRESSION_GZIP','n');config=setconfig(config,'CONFIG_INITRAMFS_COMPRESSION_NONE','y')
   (build/'.config').write_text(config)
   make=['make','-C',str(R2/'source'),'O='+str(build),'ARCH=arc','CROSS_COMPILE='+tc]
   run(make+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
   before=getconfig((R2/lane/'.config').read_text());after=getconfig((build/'.config').read_text())
   differences=[k for k in before.keys()|after.keys() if before.get(k,'n')!=after.get(k,'n')]
   require(set(differences)<=set(['CONFIG_INITRAMFS_SOURCE','CONFIG_INITRAMFS_COMPRESSION_GZIP','CONFIG_INITRAMFS_COMPRESSION_NONE']),'Unexpected kernel config change')
   require(after.get('CONFIG_INITRAMFS_COMPRESSION_NONE')=='y','FlatCPIOnotselected')
   flags='-ffile-prefix-map='+str(R2/lane)+'=/radio73-build'
   run(make+['KCFLAGS='+flags,'-j6','vmlinux','dtbs','modules'],a.output/('kernel-'+lane+'.log'),env)
   mods={f.name:sha(f) for f in build.rglob('*.ko')}
   expected={f.name:sha(f) for f in (R2/lane).rglob('*.ko')}
   require(mods==expected,'2gmoduleABIchanged')
   require(not output([tc+'nm','-u',str(build/'vmlinux')]).strip(),'Kernelundefinedsymbols')
   require(not re.search(r'\t(?:swape|llock|scond)(?:\t| )',output([tc+'objdump','-d',str(build/'vmlinux')])),'ForbiddenARCISA')
   syms={l.split()[-1]:int(l.split()[0],16) for l in output([tc+'nm',str(build/'vmlinux')]).splitlines() if len(l.split())==3}
   entry=syms['res_service'];require(syms['stext']==entry+8 and 0x8493a000<entry<syms['_end']<0x88000000,'Entry/endcontract')
   raw=a.output/('kernel-'+lane+'.raw');subprocess.run([tc+'objcopy','-O','binary',str(build/'vmlinux'),str(raw)],check=True)
   data=raw.read_bytes()
   require(0x8493a000+len(data)<0x88000000,'Decoded kernel end DDR')
   encoder=WORK/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma'
   require(sha(encoder)=='04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18','Legacy encoder identity')
   encoded_path=a.output/('kernel-'+lane+'.lzma')
   with encoded_path.open('xb') as encoded_stream:
    subprocess.run([str(encoder),'--keep','--best',str(raw),'-c'],stdout=encoded_stream,check=True,timeout=300)
   compressed=encoded_path.read_bytes()
   require(int.from_bytes(compressed[5:13],'little')==len(data),'Legacy exact decoded size')
   require(lzma.decompress(compressed,format=lzma.FORMAT_ALONE)==data,'LZMAroundtrip')
   values=[0x27051956,0,EPOCH,len(compressed),0x8493a000,entry,zlib.crc32(compressed)&0xffffffff,5,0x13,2,3,b'OpenMitraStar7.3 2G DOOM R1'.ljust(32,b'\0')]
   values[1]=zlib.crc32(struct.pack('>7I4B32s',*values))&0xffffffff
   image=struct.pack('>7I4B32s',*values)+ras_parent.read_bytes()[64:8192]+compressed
   dest=a.output/('radio73-2g-doom-autostart-'+lane+'.ras.bin');dest.write_bytes(image)
   contract=validate_bootbase_slot('2gprefixcandidate',image,0x5e0000)
   require(contract.accepted_by_contract,'Candidate exceeds prefix or Bootbasecontract')
   dtb=build/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb'
   require(sha(dtb)==parent['lanes'][0]['dtb_sha256'],'Per-unitDTchanged')
   row={'lane':lane,'kernel_sha256':sha(build/'vmlinux'),'raw_sha256':sha(raw),'raw_bytes':len(data),'image_sha256':sha(dest),'image_bytes':len(image),'image_crc32':f'{zlib.crc32(image)&0xffffffff:08x}','payload_bytes':len(compressed),'compression':3,'load':'0x8493a000','entry':hex(entry),'end':hex(syms['_end']),'dtb_sha256':sha(dtb),'config_sha256':sha(build/'.config'),'prefix_headroom':0x5e0000-len(image),'Bootbase_contract':dataclasses.asdict(contract),'module_hashes':mods}
   report['lanes'].append(row);(a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  for key in ['kernel_sha256','raw_sha256','image_sha256','dtb_sha256','config_sha256']:require(report['lanes'][0][key]==report['lanes'][1][key],'Pairdiffers:'+key)
  report.update(status='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN',classification='FLASH_CANDIDATE_NEEDS_RAM_BOOT_READBACK_ROLLBACK',builder_sha256=sha(Path(__file__)),init_source_sha256=sha(init),init_sha256=sha(root/'init'),parent_r2_receipt_sha256=sha(R2/'result.json'),game_bytes=sum(f.stat().st_size for f in (root/'www/Doom').iterdir()),dhcp='Standalone WLAN DHCP192.168.73.20-40; no gateway/DNS advertisement',limits=['CandidatefitsandcompilesbutnewflatCPIO/LZMA/autostartbootunrun.','2gdriver/source/DTpreserved; radioassociation/trafficmustrepeatwithcandidate.','ConfigurationremainsRAM; preservedstoreisuntouched/notusedforthiscandidate.','5GHznotincludedinthistemporary2gimage;R26andcommonkernelpreservedlocally.','NoSPI/MTDdriversadded; Bootbaseloadsfullinitramfsfromflashatcoldboot.','Manualmtd3safetyandcurrentmtd4readback/rollbackmustbeprovedbeforewrite.'])
 except BaseException as error:
  report.update(status='STOP_2G_FLASH_CANDIDATE',error_type=type(error).__name__,error=str(error));raise
 finally:
  (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps({'status':report['status'],'lanes':[{k:l[k] for k in ['image_bytes','image_sha256','entry','prefix_headroom']} for l in report['lanes']]}),flush=True)
if __name__=='__main__':main()
