"""Fresh paired common kernel/Realtek/Ethernet/Quantenna build, offline only.

Keeps a selected immutable R24 snapshot. It deliberately does not register the
SRAM arena or activate the 5GHz radio. A compiled module is not RF acceptance.
"""
from pathlib import Path
import argparse,datetime,hashlib,importlib.util,json,os,re,shutil,subprocess
HERE=Path(__file__).resolve().parent
WORKSPACE=Path('/workspace/user-home/Desktop/MitraStar')
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
R2=BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z'
QTN=WORKSPACE/'outputs/rea/linux73-carrier-writer-candidate-20261023T053000Z-r24'
FIVE=Path('/home/rea/openmitrastar-aelita-source-fullbuild-20261022T233000Z-r1')
EPOCH='1792365298'
RELEASE='7.3.0-openmitrastar-radio73-common-r3'
EXPECTED_ABI={'om_abi_dma_desc_size':20,'om_abi_ndev_priv':1408,'om_abi_ndev_qtn_flags':1356,'om_abi_ndev_size':1408,'om_abi_ndevstats_size':112,'om_abi_qtn_cb_size':12,'om_abi_skb_orig_dev':108,'om_abi_skb_qtn_cb':96,'om_abi_skb_recycle':112,'om_abi_skb_size':208}
def sha(p):
 with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def require(ok,message):
 if not ok:raise RuntimeError(message)
def write_json(p,data):p.write_text(json.dumps(data,indent=2)+'\n')
def output(command):return subprocess.check_output(command,text=True,stderr=subprocess.DEVNULL)
def run(command,log,env):
 print('RUN '+str(log.relative_to(log.parents[1])),flush=True)
 with log.open('xb') as stream:subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=1800)
def config_map(text):
 rows={}
 for line in text.splitlines():
  if line.startswith('CONFIG_'):key,value=line.split('=',1);rows[key]=value
  elif line.startswith('# CONFIG_') and line.endswith(' is not set'):rows[line[2:-11]]='n'
 return rows
def set_config(text,key,value):
 pattern=r'(?m)^(?:'+re.escape(key)+r'=.*|# '+re.escape(key)+r' is not set)$'
 replacement=key+'='+value
 return re.sub(pattern,replacement,text) if re.search(pattern,text) else text+'\n'+replacement+'\n'
def inspect_module(tc,p,exports):
 imports={line.split()[-1] for line in output([tc+'nm','-u',str(p)]).splitlines()}
 require(not imports-exports,'Unresolved module imports: '+p.name)
 assembly=output([tc+'objdump','-d',str(p)])
 require(not re.search(r'\t(?:swape|llock|scond)(?:\t| )',assembly),'Forbidden ARC instruction: '+p.name)

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
 require(not a.output.exists(),'Immutable output exists')
 os.umask(0o077);a.output.mkdir(mode=0o700);out=a.output
 tc=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
 require(sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263','Compiler identity changed')
 r2=json.loads((R2/'result.json').read_text())
 require(r2['status']=='PASS_PAIRED_RAM_INTEGRATION_PHYSICAL_UNRUN','Integrated R2 parent unqualified')
 require(sha(R2/'a/vmlinux')==sha(R2/'b/vmlinux')==r2['lanes'][0]['kernel_sha256'],'Integrated parent pair changed')
 require(sha(QTN/'result.json')=='4f72c9ea6fcada43e9c7a1031835703162dc6f1eb1e2b70432d5e6362be42a4c','R24 receipt changed')
 qtn=json.loads((QTN/'result.json').read_text())
 require(sha(FIVE/'kernel-context/.config')=='e709aba8ed2b55f3e6debe1480bbea2f1320c4bcd9dc3e9832c185b8e72e8efe','Qualified config changed')
 for relative,pin in qtn['files'].items():require(sha(QTN/relative.replace('\\','/'))==pin,'R24 source changed')
 require(sha(QTN/'Kbuild')==qtn['kbuild_sha256'],'R24 Kbuild changed')
 snapshot=out/'r24-source';snapshot.mkdir()
 for group in ['source','headers','providers','kernel-overlay']:shutil.copytree(QTN/group,snapshot/group)
 for name in ['Kbuild','result.json']:shutil.copyfile(QTN/name,snapshot/name)
 source=out/'kernel-source'
 env=os.environ|{'SOURCE_DATE_EPOCH':EPOCH,'KBUILD_BUILD_TIMESTAMP':'@'+EPOCH,'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73common','KBUILD_BUILD_VERSION':'1'}
 run(['cp','-a','--reflink=auto',str(R2/'source'),str(source)],out/'copy-source.log',env)
 overlay_records={}
 for relative,pin in qtn['files'].items():
  relative=relative.replace('\\','/')
  if not relative.startswith('kernel-overlay/'):continue
  rel=relative.removeprefix('kernel-overlay/');destination=source/rel
  before=sha(destination) if destination.exists() else None
  destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(snapshot/relative,destination)
  require(sha(destination)==pin,'Overlay copy mismatch')
  overlay_records[rel]={'before':before,'after':pin}
 require(sha(source/'arch/arc/boot/dts/topaz_mitrastar_eth73.dts')==sha(R2/'source/arch/arc/boot/dts/topaz_mitrastar_eth73.dts'),'Per-unit DTS changed')
 require(sha(source/'arch/arc/kernel/reset.c')==sha(R2/'source/arch/arc/kernel/reset.c'),'Reset changed outside selected scope')
 # Use the qualified 5GHz config, restore the proven private board DT name,
 # enable the integrated CGI support, and give every common module a new release.
 config=(FIVE/'kernel-context/.config').read_text()
 for key,value in [('CONFIG_INITRAMFS_SOURCE','""'),('CONFIG_BINFMT_SCRIPT','y'),('CONFIG_BUILTIN_DTB_NAME','"topaz_mitrastar_eth73"'),('CONFIG_LOCALVERSION','"-openmitrastar-radio73-common-r3"')]:
  config=set_config(config,key,value)
 required={'CONFIG_ARC_CPU_750D':'y','CONFIG_ARC_MMU_V2':'y','CONFIG_ARC_PAGE_SIZE_8K':'y','CONFIG_PREEMPT_NONE':'y','CONFIG_ARC_PLAT_TOPAZ_BASIC':'y','CONFIG_OPENMITRASTAR_QDRV_COMPAT':'y','CONFIG_CRYPTO_LIB_SHA256':'y','CONFIG_IPV6':'y','CONFIG_NET_SCHED':'y','CONFIG_BRIDGE':'m','CONFIG_GPIOLIB':'y','CONFIG_I2C':'y'}
 for name,value in required.items():require(config_map(config).get(name)==value,'Required shared configuration absent: '+name)
 require(config_map(config).get('CONFIG_MODULE_FORCE_UNLOAD','n')=='n','Forced unload forbidden')
 (out/'common.config').write_text(config)
 abi_spec=importlib.util.spec_from_file_location('qualified_abi',WORKSPACE/'tools/audit_hgw5g_linux73_pair_abi.py')
 module=importlib.util.module_from_spec(abi_spec);abi_spec.loader.exec_module(module)
 gpl=WORKSPACE/'work/sources/Quantenna-GPL'
 require(gpl.is_dir(),'Qualified GPL include source absent')
 result={'schema':'openmitrastar.common-radio73-context/v1','status':'RUNNING_OFFLINE_COMMON_KERNEL_PAIR','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hardware_accessed':False,'firmware_eligible':False,'physical_boot':'UNRUN','SRAM_registration':False,'radio5g_activation':False,'release':RELEASE,'parent_r2_result_sha256':sha(R2/'result.json'),'r24_result_sha256':sha(snapshot/'result.json'),'kernel_overlay':overlay_records,'lanes':[]}
 write_json(out/'result.json',result)
 try:
  for lane in ['a','b']:
   directory=out/lane;directory.mkdir();kernel=directory/'kernel';kernel.mkdir()
   (kernel/'.config').write_text(config)
   flags='-ffile-prefix-map='+str(directory)+'=/radio73-common-build -fmacro-prefix-map='+str(directory)+'=/radio73-common-build'
   lane_env=env|{'KCFLAGS':flags}
   make=['make','-C',str(source),'O='+str(kernel),'ARCH=arc','CROSS_COMPILE='+tc]
   run(make+['olddefconfig'],directory/'configure.log',lane_env)
   final=config_map((kernel/'.config').read_text())
   for name,value in required.items():require(final.get(name)==value,'Required config lost: '+name)
   require(final.get('CONFIG_BINFMT_SCRIPT')=='y' and final.get('CONFIG_BUILTIN_DTB_NAME')=='"topaz_mitrastar_eth73"','Runtime/DT selection lost')
   run(make+['-j6','vmlinux','modules','dtbs'],directory/'kernel.log',lane_env)
   native=directory/'native';native.mkdir()
   for group in ['source','headers','providers']:shutil.copytree(snapshot/group,native/group)
   shutil.copyfile(snapshot/'Kbuild',native/'Kbuild')
   run(make+['M='+str(native),'QTN_GPL='+str(gpl),'-j6','modules'],directory/'native.log',lane_env)
   native_mods=sorted(native.glob('*.ko'))
   c_objects=sorted((native/'source').rglob('*.o'))+sorted((native/'providers').rglob('*.o'))
   require(len(native_mods)==22 and len(c_objects)==74,'Native module/object closure changed')
   for relative,pin in qtn['files'].items():
    relative=relative.replace('\\','/')
    if relative.split('/')[0] in ['source','headers','providers']:require(sha(native/relative)==pin,'Native source modified by build')
   emac=directory/'emac';shutil.copytree(WORKSPACE/'work/kernel-port/linux-7.3-radioeth-ram-v1/candidate/driver',emac)
   run(make+['M='+str(emac),'-j6','modules'],directory/'emac.log',lane_env)
   witness=directory/'abi';witness.mkdir()
   (witness/'abi_probe.c').write_text(module.ABI)
   includes=[native/'headers',native/'source/qdrv/compat/include',gpl,gpl/'include',gpl/'common']
   (witness/'Kbuild').write_text('obj-m := abi_probe.o\nccflags-y += '+' '.join('-I'+str(p) for p in includes)+'\n')
   run(make+['M='+str(witness),'abi_probe.o'],directory/'abi.log',lane_env)
   nm=output([tc+'nm','-S',str(witness/'abi_probe.o')])
   values={m.group(2):int(m.group(1),16)-1 for m in re.finditer(r'^[0-9a-f]+\s+([0-9a-f]+)\s+[BbDd]\s+(om_abi_\S+)$',nm,re.M)}
   require(values==EXPECTED_ABI,'Actual ARC common ABI differs from qualified R24')
   exports={l.split()[1] for path in [kernel/'Module.symvers',native/'Module.symvers'] for l in path.read_text().splitlines()}
   modules=sorted(kernel.rglob('*.ko'))+native_mods+[emac/'qtn-topaz-emac-eth73.ko']
   for p in modules:inspect_module(tc,p,exports)
   release_text=(kernel/'include/generated/utsrelease.h').read_text()
   require('"'+RELEASE+'"' in release_text,'Common module release differs')
   require(not output([tc+'nm','-u',str(kernel/'vmlinux')]).strip(),'Unresolved common kernel imports')
   require(not re.search(r'\t(?:swape|llock|scond)(?:\t| )',output([tc+'objdump','-d',str(kernel/'vmlinux')])),'Forbidden ARC kernel instruction')
   dtb=kernel/'arch/arc/boot/dts/topaz_mitrastar_eth73.dtb'
   require(sha(dtb)==r2['lanes'][0]['dtb_sha256'],'Common per-unit DTB changed')
   record={'name':lane,'ABI':values,'kernel_sha256':sha(kernel/'vmlinux'),'config_sha256':sha(kernel/'.config'),'symvers_sha256':sha(kernel/'Module.symvers'),'dtb_sha256':sha(dtb),'kernel_module_count':len(list(kernel.rglob('*.ko'))),'native_module_count':22,'native_C_units':74,'module_count':len(modules),'modules':{p.relative_to(directory).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in modules},'native_C_objects':{p.relative_to(native).as_posix():sha(p) for p in c_objects},'strong_imports_resolved':True,'forbidden_ISA':False}
   result['lanes'].append(record);write_json(out/'result.json',result)
   print('PASS common lane '+lane,flush=True)
  left,right=result['lanes']
  keys=['ABI','kernel_sha256','config_sha256','symvers_sha256','dtb_sha256','modules','native_C_objects']
  mismatch=[key for key in keys if left[key]!=right[key]]
  require(not mismatch,'Paired common artifacts differ: '+','.join(mismatch))
  result.update(status='PASS_PAIRED_COMMON_KERNEL_REALTEK_ETHERNET_R24_22_NATIVE_ABI',pair_identical=True,limits=['Offline common context only; no initramfs/Bootbase package or physical boot yet.','SRAM board reservation remains closed; no claim that 5GHz loads or transmits.','All existing radio/client/TLS/traffic evidence refers to previous physical image; repeat after common ABI change.','Complete persistent fit/store/recovery/soak/release remains required.'])
 except BaseException as e:
  result.update(status='STOP_COMMON_CONTEXT_BUILD',error_type=type(e).__name__,error=str(e));raise
 finally:
  result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();result['builder_sha256']=sha(Path(__file__))
  write_json(out/'result.json',result)
  print(json.dumps({'status':result['status'],'output':str(out),'completed_lanes':len(result['lanes'])}),flush=True)
if __name__=='__main__':main()
