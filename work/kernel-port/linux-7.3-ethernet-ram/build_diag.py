#!/usr/bin/env python3
"""Integrate exact ETH73 module and syscall-only PID1 in a RAM trial image.
Builds offline from the paired kernel; no UART, network or flash operations.
"""
import argparse,hashlib,json,os,re,shutil,struct,subprocess,tarfile,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ELF_SHA='3c173455469c84ed46664a9f3b36b80dfd112ab77b77cc1f755413cbb2a6e19a'
MOD_SHA='067f040165348edcdc3d125cf284f6921802cc3590909df9fe3772c0b9adf798'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as stream:subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--private-dtb',type=Path,required=True);p.add_argument('--template',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='eth73',KBUILD_BUILD_VERSION='1')
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-')
 assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 for lane in ['a','b']:assert sha(a.base/lane/'vmlinux')==ELF_SHA and sha(a.base/('module-'+lane)/'qtn-topaz-emac-eth73.ko')==MOD_SHA
 source=a.output/'source'
 run(['cp','-a','--reflink=auto',str(a.source),str(source)],a.output/'copy-source.log',env)
 # Private DTB contains the established unit MAC. Do not print or publish it.
 dtctool=a.base/'a/scripts/dtc/dtc'
 private=subprocess.check_output([str(dtctool),'-I','dtb','-O','dts',str(a.private_dtb)],stderr=subprocess.DEVNULL,text=True)
 hit=re.search(r'ethernet@e8000000 \{(.*?)\n\s*\};',private,re.S);assert hit
 mac=re.search(r'local-mac-address = \[([0-9a-f ]+)\];',hit[1]);assert mac
 address=bytes.fromhex(mac[1]);assert len(address)==6 and address!=bytes(6) and not address[0]&1
 dt=source/'arch/arc/boot/dts/topaz_mitrastar_eth73.dts';s=dt.read_text();assert s.count('status = "disabled";')==1
 s=s.replace('status = "disabled";', 'local-mac-address = ['+mac[1]+'];\n\t\t\tstatus = "okay";');dt.write_text(s)
 ir=a.output/'initramfs';ir.mkdir()
 shutil.copyfile(HERE/'init.c',ir/'eth73_init.c')
 run([tc+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Werror','-Wl,-e,_start','-Wl,--build-id=none','-o',str(ir/'init'),str(ir/'eth73_init.c')],a.output/'init-build.log',env)
 mod=ir/'qtn-topaz-emac-eth73.ko';shutil.copyfile(a.base/'module-a/qtn-topaz-emac-eth73.ko',mod)
 listing=ir/'list';listing.write_text('dir /dev 755 0 0\ndir /proc 755 0 0\ndir /sys 755 0 0\nnod /dev/console 600 0 0 c 5 1\nnod /dev/ttyS0 600 0 0 c 4 64\nfile /init '+str(ir/'init')+' 755 0 0\nfile /qtn-topaz-emac-eth73.ko '+str(mod)+' 644 0 0\n')
 lanes=[]
 for lane in ['a','b']:
  out=a.output/lane
  run(['cp','-a','--reflink=auto',str(a.base/lane),str(out)],a.output/('copy-build-'+lane+'.log'),env)
  config=(out/'.config').read_text();config=re.sub(r'CONFIG_INITRAMFS_SOURCE=".*"','CONFIG_INITRAMFS_SOURCE="'+str(listing)+'"',config);(out/'.config').write_text(config)
  # Make resets source location in copied O= wrappers; build final ELF/DT only.
  make=['make','-C',str(source),'O='+str(out),'ARCH=arc','CROSS_COMPILE='+tc]
  run(make+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
  run(make+['KCFLAGS=-ffile-prefix-map='+str(out)+'=/eth73-build -ffile-prefix-map='+str(a.base/('module-'+lane))+'=/eth73-module','-j6','vmlinux','dtbs'],a.output/('build-'+lane+'.log'),env)
  elf=out/'vmlinux'
  for f in [elf,ir/'init',mod]:
   asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  assert not subprocess.check_output([tc+'nm','-u',str(elf)],text=True).strip()
  table=subprocess.check_output([tc+'nm',str(elf)],text=True)
  syms={l.split()[-1]:int(l.split()[0],16) for l in table.splitlines() if len(l.split())==3}
  entry=syms['res_service']
  assert 0x8493a000<entry<0x84950000 and syms['stext']==entry+8 and syms['_end']<0x88000000
  raw=a.output/('kernel-'+lane+'.raw');subprocess.run([tc+'objcopy','-O','binary',str(elf),str(raw)],check=True)
  payload=raw.read_bytes();assert len(payload)<0x1000000
  template=a.template.read_bytes();assert sha(a.template)=='81bbb0098f66c453c3282185ac337761a89d174950b341c6c5a6572ba4034719'
  fields=[0x27051956,0,1792365298,len(payload),0x8493a000,entry,zlib.crc32(payload)&0xffffffff,5,0x13,2,0,b'OpenMitraStar 7.3 ETH RAM'.ljust(32,b'\0')]
  fields[1]=zlib.crc32(struct.pack('>7I4B32s',*fields))&0xffffffff
  image=struct.pack('>7I4B32s',*fields)+template[64:8192]+payload
  (a.output/('eth73-'+lane+'.ras.bin')).write_bytes(image)
  lanes.append({'lane':lane,'entry':hex(entry),'load':'0x8493a000','vmlinux_sha256':sha(elf),'vmlinux_bytes':elf.stat().st_size,'payload_bytes':len(payload),'raw_sha256':sha(raw),'image_sha256':hashlib.sha256(image).hexdigest(),'image_bytes':len(image),'image_crc32':f'{zlib.crc32(image)&0xffffffff:08x}','end':hex(syms['_end']),'config_sha256':sha(out/'.config'),'dtb_sha256':sha(out/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb')})
 assert all(lanes[0][k]==lanes[1][k] for k in ['vmlinux_sha256','raw_sha256','image_sha256','config_sha256','dtb_sha256'])
 report={'schema':'openmitrastar.eth73-ram-integration/v1','status':'PASS_PAIRED_INCREMENTAL_RAM_BUILD_PHYSICAL_UNRUN','hardware_accessed':False,'module_sha256':MOD_SHA,'init_sha256':sha(ir/'init'),'init_bytes':(ir/'init').stat().st_size,'lanes':lanes,'per_unit_identity_preserved':True,'private_dtb_sha256':sha(a.private_dtb),'dt_ethernet_enabled':True,'module_embedded':True,'driver_loading':'EXPLICIT_UART_ETHLOAD_ONLY','flash_writes':0,'bootenv_writes':0,'build_mode':'Incremental from sealed paired Ethernet baseline; fresh source and O= copies, no source deletion.'}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
