"""Compose F361 plus qualified F352 Ethernet only; preserve current store."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,hashlib,io,json,shutil,subprocess,zlib
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f362_rootfs_worker import VERSION
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f361-f358-config-persistence-device-bound'
OLD='openmitrastar-linux510-f361-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
BASE='openmitrastar-linux510-f362-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
OVERLAY=ROOT/'work/kernel-port/versions/f362-dual-ethernet/overlay'
F352=ROOT/'outputs/kernel-port/f352-qualified-20260921T163718Z/result.json'
F352_SOURCE=ROOT/'work/kernel-port/modules/f352_dual_emac'
STORE=DEVICE/'analysis/f361-store-seq2-20260921T193734Z/store.bin'
EPOCH=1790006400

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def crc(b):return f'{zlib.crc32(b)&0xffffffff:08x}'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--kernel-result',type=Path,required=True);args=ap.parse_args()
 assert shutil.disk_usage('C:/').free>500*1024*1024
 assert sha(SOURCE/(OLD+'.webformat.bin'))=='0c46aa0232129694097adf7b5e761bf2f633b4dd877787525d15610461b302af'
 assert sha(F352)=='957aadf65852c479a21a171581a3b8ae08190d518b094941512c6387bdf5dd13'
 source=json.loads((SOURCE/'manifest.json').read_text());ethernet=json.loads(F352.read_text());kr=json.loads(args.kernel_result.read_text());kernel=args.kernel_result.resolve().parent
 assert kr['status']=='PASS_OFFLINE_DT_ONLY_KERNEL' and kr['config_unchanged'] and kr['exports_unchanged']
 for row in kr['artifacts'].values():assert sha(row['path'])==row['sha256']
 assert sha(ethernet['artifact']['path'])==ethernet['artifact']['sha256']
 assert sha(STORE)=='fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873'
 store=STORE.read_bytes();assert len(store)==0x1c0000 and crc(store)=='5d2ee646'
 fallback=(SOURCE/(OLD+'.webformat.bin')).read_bytes();fallback_prefix=fallback+b'\xff'*(0x5e0000-len(fallback))
 assert crc(fallback_prefix)=='4cb7f99e' and crc(fallback_prefix+store)=='815b9440'
 final=DEVICE/'firmware/f362-f361-dual-ethernet-device-bound';assert not final.exists()
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f362-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f362_rootfs_worker.py',ROOT/'tools/build_f362_dual_ethernet_kernel.py',F352,STORE,SOURCE/'manifest.json',args.kernel_result,F352_SOURCE/'om-ethernet-f352',F352_SOURCE/'S56-f352-ethernet']}
 inputs.update({str(p):sha(p) for p in OVERLAY.rglob('*') if p.is_file()});build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 fields={'f362.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','f362.raw.bin':'kernel-squashfs.raw.bin','f362.config':'kernel-squashfs.config','f362.dtb':'topaz_mitrastar_squashfs.dtb','f362.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 compressor=ROOT/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma'
 assert sha(compressor)=='04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18'
 compressed=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e',linux(compressor),'--keep','--best',linux(kernel/'f362.raw.bin'),'-c'],capture_output=True,check=True)
 (out/'kernel.lzma').write_bytes(compressed.stdout)
 for lane in ['a','b']:
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory=out/lane/'rootfs-inventory.json'
  for name,target in fields.items():shutil.copyfile(kernel/name,assets/target)
  shutil.copyfile(out/'kernel.lzma',assets/'kernel-squashfs.lzma')
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f362_rootfs_worker.py'),'--source',linux(SOURCE/(OLD+'.rootfs.squashfs')),'--source-sha',source['artifacts']['rootfs_squashfs']['sha256'],'--overlay',linux(OVERLAY),'--module',linux(ethernet['artifact']['path']),'--helper',linux(F352_SOURCE/'om-ethernet-f352'),'--service',linux(F352_SOURCE/'S56-f352-ethernet'),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
  run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr);assert not run.returncode,run.stderr.decode(errors='replace')[-1500:]
  settings={'ASSETS':assets,'OUT':build,'BASE':BASE,'ROOTFS_WINDOW':0x460000,'SOURCE_DATE_EPOCH':EPOCH};saved={k:getattr(compose,k) for k in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   for k,v in settings.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=SOURCE/(OLD+'.webformat.bin')
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   compose.f71.TEMPLATE=template
   for k,v in saved.items():setattr(compose,k,v)
  (out/lane/'composition.log').write_text(log.getvalue());assert not rc
  m=json.loads((build/'manifest.json').read_text());delta=json.loads(inventory.read_text());image=build/(BASE+'.webformat.bin');body=image.read_bytes();assert len(body)<=0x5e0000 and m['contracts']['bootbase']=='PASS'
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store
  m.update(schema='openmitrastar.f362-dual-ethernet/v1',classification='F361_WITH_F352_DUAL_ETHERNET_ONLY',product_version=VERSION,firmware_build_id=build_id,generated_at_utc=stamp,candidate_eligible=True,release_eligible=False,flash_supported=False,
   source={'firmware':'F361 exact','image_sha256':sha(SOURCE/(OLD+'.webformat.bin')),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},frontend=source['frontend'],device_identity=source['device_identity'],web_identity=source['web_identity'],web_security=source['web_security'],
   watchdog=source['watchdog'],module_closure={**source['module_closure'],'f352_imports_resolved':kr['module_imports_resolved'],'f358_exports_unchanged':True},config_backend=source['config_backend'],
   change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'kernel':'F358 C/config/build identity preserved; embedded Ethernet DT compatible and f352 property only','dt':kr['dt_delta'],'radio_application_unchanged':True,'om_network_base_unchanged':True,'primary_identity_unchanged':True,'supervisor_unchanged':True},
   ethernet={'module':ethernet['artifact'],'qualification':{'path':str(F352),'sha256':sha(F352),'core_tests_reused':4933,'bridge_tests_reused':12},'netdevs':[{'name':'eth0','mac':1,'phy':3},{'name':'eth1','mac':0,'phy':1}],'loader':'S15-f352-driver /usr/sbin/ram-insmod-qtn','attach':'S56-f352-ethernet --attach','secondary_mac':'derive from live primary, OEM first byte +2 before eth1 up','dt_status':'okay','physical_acceptance':'UNRUN'},
   preserved_store={'path':str(STORE),'sha256':sha(STORE),'bytes':len(store),'crc32':crc(store),'must_match_before_and_after_firmware_boot':True},
   recovery={'image':str(SOURCE/(OLD+'.webformat.bin')),'sha256':sha(SOURCE/(OLD+'.webformat.bin')),'bytes':len(fallback),'version':source['product_version'],'kernel_build':'#358','full_slot_crc32_with_preserved_store':crc(fallback_prefix+store),'prefix_crc32':crc(fallback_prefix),'store_must_be_preserved':True},
   reproducibility={'kernel_c_objects_reused':True,'kernel_relink':str(args.kernel_result),'rootfs_repacked_twice':True,'epoch':EPOCH},physical_validation={'status':'NOT_RUN','wifi_tests':'DEFERRED'},safety={'hardware_actions':False,'firmware_erase_end_exclusive':'0xdc0000','write_prefix_bytes':0x5e0000,'normal_write_target':'physical mtd4/linux_live at 0x7e0000','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],'startup_flash_writes':False,'flash_go_no_go':'OFFLINE_GO_PHYSICAL_RECOVERY_AND_INSTALLER_GATE_PENDING'})
  m['artifacts']['full_slot']={'bytes':len(full),'sha256':hashlib.sha256(full).hexdigest(),'crc32':crc(full),'store_source':'preserved F361 seq2 journal, not FF padding'}
  m['layout']['firmware_prefix_crc32']=crc(prefix)
  (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inventory,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f361',build/'known_hosts.f362')
  (build/'LAYOUT.md').write_text('# F362 dual Ethernet integration\n\nF361 plus qualified F352 dual Ethernet module/helper and the matching enabled Ethernet DT. F358 C objects/config/build identity and supervisor preserved. Only mtd4 prefix 0x7e0000+0x5e0000 may be installed after recovery and installer gates. Preserve DC/DD store and protected partitions. Exact F361 fallback uses the same seq2 store. Physical boot/ports/traffic acceptance remains unrun; Wi-Fi deferred.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in ['.webformat.bin','.rootfs.squashfs','.kernel.raw.bin','.kernel.lzma','.config','.dtb','.vmlinux']:assert sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix))
 assert (out/'a/rootfs-inventory.json').read_bytes()==(out/'b/rootfs-inventory.json').read_bytes()
 for p,digest in inputs.items():assert sha(p)==digest
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text());image=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f362-image-build/v1','status':'PASS_OFFLINE_DUAL_ETHERNET_IMAGE','artifact':{'path':str(image),'bytes':image.stat().st_size,'sha256':sha(image)},'manifest_sha256':sha(final/'manifest.json'),'product_version':VERSION,'firmware_build_id':build_id,'kernel_build':'#358','kernel_result':str(args.kernel_result),'reproducible_rootfs_and_image':True,'bootbase':'PASS','slot_fit':True,'prefix_crc32':m['layout']['firmware_prefix_crc32'],'full_slot':m['artifacts']['full_slot'],'preserved_store':m['preserved_store'],'rootfs_changed_files':m['change_scope']['files'],'hardware_actions':False,'startup_flash_writes':False,'automatic_arm':False,'automatic_reboot':False,'recovery':m['recovery'],'flash_go_no_go':m['safety']['flash_go_no_go']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'result':str(out/'result.json')},indent=2))
if __name__=='__main__':main()
