"""Compose persistent F361 userspace integration, preserving kernel and current journal."""
from pathlib import Path
from datetime import datetime,timezone
import contextlib,hashlib,io,json,shutil,subprocess,zlib
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f361_rootfs_worker import VERSION
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f358-f340-config-backend-device-bound'
OLD='openmitrastar-linux510-f358-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
BASE='openmitrastar-linux510-f361-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
OVERLAY=ROOT/'work/kernel-port/versions/f361-config-integration/overlay'
READER=ROOT/'outputs/userspace/f361-journal-reader-20260921T191025Z/result.json'
TESTS=ROOT/'outputs/preflight/f361-integration-20260921T191411Z/result.json'
STORE=DEVICE/'analysis/f360-expected-config-20260921T182322Z/expected-store.bin'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 assert shutil.disk_usage('C:/').free>500*1024*1024
 assert sha(SOURCE/(OLD+'.webformat.bin'))=='fe2ff28a8b083a72a089e8180d973727cea033673348a767a73595b440099e6f'
 assert sha(SOURCE/'manifest.json')=='b2c7a79796481b324b6ba4d4d84c82a6a017c96f2a6967bed3c03fe292845652'
 source=json.loads((SOURCE/'manifest.json').read_text());reader=json.loads(READER.read_text());tests=json.loads(TESTS.read_text())
 assert reader['status']=='PASS_OFFLINE_ROM_READER_BUILD' and reader['reproducible'] and sha(reader['artifact']['path'])==reader['artifact']['sha256']
 assert tests['status']=='PASS' and tests['count']==8
 assert sha(STORE)=='a7620cf8f6a8a8764e082e524c1968915e0ad4b6810be939522deed67b0302a8'
 real_reader=ROOT/'outputs/handoff-live/f361-reader-20260921T191143Z/result.json';assert real_reader.is_file()
 final=DEVICE/'firmware/f361-f358-config-persistence-device-bound';assert not final.exists()
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f361-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f361_rootfs_worker.py',READER,TESTS,real_reader,STORE,SOURCE/'manifest.json']}
 inputs.update({str(p):sha(p) for p in OVERLAY.rglob('*') if p.is_file()});build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 fields={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 for lane in ['a','b']:
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory=out/lane/'rootfs-inventory.json'
  for suffix,name in fields.items():shutil.copyfile(SOURCE/(OLD+suffix),assets/name)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f361_rootfs_worker.py'),'--source',linux(SOURCE/(OLD+'.rootfs.squashfs')),'--source-sha',source['artifacts']['rootfs_squashfs']['sha256'],'--overlay',linux(OVERLAY),'--reader',linux(reader['artifact']['path']),'--reader-sha',reader['artifact']['sha256'],'--build-id',build_id,'--epoch','1790006400','--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
  run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr);assert not run.returncode,run.stderr.decode(errors='replace')[-1500:]
  settings={'ASSETS':assets,'OUT':build,'BASE':BASE,'ROOTFS_WINDOW':0x460000,'SOURCE_DATE_EPOCH':1790006400};saved={k:getattr(compose,k) for k in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   for k,v in settings.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=SOURCE/(OLD+'.webformat.bin')
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   compose.f71.TEMPLATE=template
   for k,v in saved.items():setattr(compose,k,v)
  (out/lane/'composition.log').write_text(log.getvalue());assert not rc
  m=json.loads((build/'manifest.json').read_text());delta=json.loads(inventory.read_text());image=build/(BASE+'.webformat.bin');body=image.read_bytes();assert len(body)<=0x5e0000 and m['contracts']['bootbase']=='PASS'
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+STORE.read_bytes()
  m.update(schema='openmitrastar.f361-config-persistence/v1',classification='F358_WITH_BOOT_JOURNAL_CONSUMER_AND_EXPLICIT_API_SAVE',product_version=VERSION,firmware_build_id=build_id,generated_at_utc=stamp,candidate_eligible=False,release_eligible=False,flash_supported=False,
   source={'firmware':'F358 exact','image_sha256':sha(SOURCE/(OLD+'.webformat.bin')),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},frontend=source['frontend'],device_identity=source['device_identity'],web_identity=source['web_identity'],web_security=source['web_security'],
   watchdog=source['watchdog'],module_closure=source['module_closure'],
   change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'kernel_config_dt_supervisor':'byte-identical F358','radio_application_unchanged':True},
   config_backend={'boot_consumer':'MTD ROM immutable snapshot and F342 validation','managed_settings':22,'derived_fields_ignored':['ORIGIN_MTD5_IMPORTED','RADIO5G_SSID','RADIO5G_CONFIG_SOURCE'],'empty_corrupt_policy':'fallback, no erase/format/save','module_autoload':True,'module_init_mmio':False,'automatic_writes':False,'explicit_save_api':'config/store action=commit','radio_transaction_commit':'volatile','automatic_arm':False,'automatic_reboot':False,'automatic_bus_fault_recovery':False,'rollback_supported':False},
   preserved_store={'path':str(STORE),'sha256':sha(STORE),'bytes':STORE.stat().st_size,'crc32':'31bf4416','must_match_before_and_after_firmware_boot':True},
   recovery={'image':str(SOURCE/(OLD+'.webformat.bin')),'sha256':sha(SOURCE/(OLD+'.webformat.bin')),'bytes':(SOURCE/(OLD+'.webformat.bin')).stat().st_size,'version':source['product_version'],'kernel_build':'#358','full_slot_crc32_with_preserved_store':'3e8db0dc','store_must_be_preserved':True},
   reproducibility={'kernel_recompiled':False,'rootfs_repacked_twice':True},physical_validation={'status':'NOT_RUN','reader_only_real_pass':str(real_reader),'wifi_tests':'DEFERRED'},safety={'hardware_actions':False,'firmware_erase_end_exclusive':'0xdc0000','write_prefix_bytes':0x5e0000,'startup_spi_commands':False,'startup_flash_writes':False,'flash_go_no_go':'ROOT_INSTALLER_REVIEW_PENDING'})
  m['artifacts']['full_slot']={'bytes':len(full),'sha256':hashlib.sha256(full).hexdigest(),'crc32':f'{zlib.crc32(full)&0xffffffff:08x}','store_source':'preserved F360 journal, not FF padding'}
  m['layout']['firmware_prefix_crc32']=f'{zlib.crc32(prefix)&0xffffffff:08x}'
  (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inventory,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f358',build/'known_hosts.f361')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in ['.webformat.bin','.rootfs.squashfs','.kernel.raw.bin','.kernel.lzma','.config','.dtb','.vmlinux']:assert sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix))
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text());image=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f361-image-build/v1','status':'PASS_OFFLINE_CONFIG_PERSISTENCE_IMAGE','artifact':{'path':str(image),'bytes':image.stat().st_size,'sha256':sha(image)},'manifest_sha256':sha(final/'manifest.json'),'product_version':VERSION,'firmware_build_id':build_id,'kernel_build':'#358','kernel_config_dt_supervisor_unchanged':True,'reproducible':True,'bootbase':'PASS','slot_fit':True,'prefix_crc32':m['layout']['firmware_prefix_crc32'],'full_slot':m['artifacts']['full_slot'],'preserved_store':m['preserved_store'],'integration_tests':8,'hardware_actions':False,'startup_flash_writes':False,'automatic_arm':False,'automatic_reboot':False,'recovery':m['recovery']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'result':str(out/'result.json')},indent=2))
if __name__=='__main__':main()
