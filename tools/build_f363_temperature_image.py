"""Compose an inactive-by-default F363 temperature diagnostic image from F362."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,hashlib,io,json,shutil,subprocess,zlib
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f363_rootfs_worker import VERSION
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f362-f361-dual-ethernet-device-bound'
OLD='openmitrastar-linux510-f362-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
BASE='openmitrastar-linux510-f363-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
OVERLAY=ROOT/'work/kernel-port/versions/f363-temperature-diagnostic/overlay'
STORE=DEVICE/'analysis/f361-store-seq2-20260921T193734Z/store.bin'
F339=ROOT/'outputs/kernel-port/f339-hwmon-qualified-20260921T134348Z/result.json'
EPOCH=1790006400
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def crc(b):return f'{zlib.crc32(b)&0xffffffff:08x}'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--components',required=True,type=Path);ap.add_argument('--integration-test',required=True,type=Path);ap.add_argument('--helper-test',required=True,type=Path);a=ap.parse_args()
 assert shutil.disk_usage(ROOT).free>500*1024*1024
 source=json.loads((SOURCE/'manifest.json').read_text());components=json.loads(a.components.read_text());test=json.loads(a.integration_test.read_text())
 assert sha(SOURCE/(OLD+'.webformat.bin'))=='9582b92f1c68ec192ee14c55ba9ab69015749cc69ecde392bd6ad3392d105f2b'
 assert sha(SOURCE/'manifest.json')=='8e576d3d5f4676dcf5287d8dc640784a7756daf9af2a9ce77c585c1eb3300957'
 assert components['status']=='PASS_OFFLINE_TEMPERATURE_INTEGRATION' and test['status']=='PASS_F363_DRIVER_CONSUMER_INTEGRATION'
 helper_test=json.loads(a.helper_test.read_text());assert helper_test['status']=='PASS_F363_HELPER_FAKE_SYSFS' and helper_test['production_sha256']==sha(OVERLAY/'usr/sbin/om-temperature-f363')
 assert test['driver_sha256']==components['source_pins']['sensor-source\\temp_sens.c'] and test['core_sha256']==components['source_pins']['sensor-source\\topaz_temp_core.h']
 assert test['qdrv_sha256']==components['source_pins']['qdrv-source\\qdrv\\qdrv_wlan.c']
 for row in components['artifacts'].values():assert sha(row['path'])==row['sha256']
 assert sha(STORE)=='fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873'
 store=STORE.read_bytes();assert len(store)==0x1c0000 and crc(store)=='5d2ee646'
 fallback=(SOURCE/(OLD+'.webformat.bin')).read_bytes();fallback_prefix=fallback+b'\xff'*(0x5e0000-len(fallback));assert crc(fallback_prefix+store)=='1a6e28c0'
 final=DEVICE/'firmware/f363-f362-temperature-diagnostic-device-bound';assert not final.exists()
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f363-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f363_rootfs_worker.py',a.components,a.integration_test,a.helper_test,F339,STORE,SOURCE/'manifest.json']}
 inputs.update({str(p):sha(p) for p in OVERLAY.rglob('*') if p.is_file()});build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 kernel=a.components.parent
 fields={'f363.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','f363.raw.bin':'kernel-squashfs.raw.bin','f363.config':'kernel-squashfs.config','f363.dtb':'topaz_mitrastar_squashfs.dtb','f363.vmlinux':'kernel-squashfs.vmlinux'}
 sensor=Path(components['artifacts']['a/sensor/temp_sens.ko']['path']);qdrv=Path(components['artifacts']['a/temperature/qdrv/qdrv.ko']['path']);hwmon=Path(components['artifacts']['hwmon.ko']['path'])
 print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 compressor=ROOT/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma';assert sha(compressor)=='04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18'
 packed_kernel=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e',linux(compressor),'--keep','--best',linux(kernel/'f363.raw.bin'),'-c'],capture_output=True,check=True)
 (out/'kernel.lzma').write_bytes(packed_kernel.stdout)
 for lane in ('a','b'):
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory=out/lane/'rootfs-inventory.json'
  for n,target in fields.items():shutil.copyfile(kernel/n,assets/target)
  shutil.copyfile(out/'kernel.lzma',assets/'kernel-squashfs.lzma')
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f363_rootfs_worker.py'),'--source',linux(SOURCE/(OLD+'.rootfs.squashfs')),'--source-sha',source['artifacts']['rootfs_squashfs']['sha256'],'--overlay',linux(OVERLAY),'--hwmon',linux(hwmon),'--sensor',linux(sensor),'--qdrv',linux(qdrv),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
  run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr)
  assert not run.returncode,run.stderr.decode(errors='replace')[-1500:]
  settings={'ASSETS':assets,'OUT':build,'BASE':BASE,'ROOTFS_WINDOW':0x460000,'SOURCE_DATE_EPOCH':EPOCH};saved={k:getattr(compose,k) for k in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   for k,v in settings.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=SOURCE/(OLD+'.webformat.bin')
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   compose.f71.TEMPLATE=template
   for k,v in saved.items():setattr(compose,k,v)
  (out/lane/'composition.log').write_text(log.getvalue());assert not rc
  m=json.loads((build/'manifest.json').read_text());delta=json.loads(inventory.read_text());image=build/(BASE+'.webformat.bin');body=image.read_bytes();assert len(body)<0x5e0000 and m['contracts']['bootbase']=='PASS'
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store
  m.update(schema='openmitrastar.f363-temperature-image/v1',classification='F362_WITH_EXPLICIT_TEMPERATURE_DIAGNOSTIC',product_version=VERSION,firmware_build_id=build_id,generated_at_utc=stamp,candidate_eligible=True,release_eligible=False,flash_supported=False,
   source={'firmware':'F362 exact','image_sha256':sha(SOURCE/(OLD+'.webformat.bin')),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},frontend=source['frontend'],device_identity=source['device_identity'],web_identity=source['web_identity'],web_security=source['web_security'],
   watchdog=source['watchdog'],config_backend=source['config_backend'],ethernet=source['ethernet'],
   module_closure={'all_f340_exports_preserved':True,'f358_exports_preserved':True,'kernel_module_symvers_sha256':sha(kernel/'Module.symvers'),'f352_imports_resolved':source['module_closure']['f352_imports_resolved'],'provider_imports_resolved':True,'original_modules_unchanged':False,'unchanged_existing_modules_except':['qdrv','temp_sens'],'added_modules':['hwmon'],'temperature_components':{'path':str(a.components),'sha256':sha(a.components)},'qdrv_original_internal_radar_profile':True,'f355_included':False},
   temperature={'source_qualification':{'path':str(F339),'sha256':sha(F339),'full_oracle_reused':True},'integration_test':{'path':str(a.integration_test),'sha256':sha(a.integration_test)},'sensor_module':{'path':str(sensor),'runtime_path':'/'+ 'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/temp_sens.ko','sha256':sha(sensor),'bytes':sensor.stat().st_size},'hwmon_module':{'path':str(hwmon),'runtime_path':'/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/hwmon.ko','sha256':sha(hwmon),'bytes':hwmon.stat().st_size},'default_sensor_mmio':False,'default_enabled':False,'status_attributes':{'enabled':0,'activation_attempted':0,'activation_error':-19},'enable':'om-temperature-f363 enable','read':'om-temperature-f363 read','physical_clock_or_sensor_qualified':False,'core_sha256':test['core_sha256'],'kernel_config_change':'CONFIG_HWMON=m','new_shutdown_protocol':False},
   change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'dt':components['dt_delta'],'recovery_reg_tail_preserved':True,'irq_pcie_shared_maps':components['shared_sysctl_maps_reviewed'],'qdrv_comparisons':components['qdrv_comparisons'],'necessary_wps_abi_rebuild':'task_struct offsets match current kernel; no WPS feature activation/test','ethernet_unchanged':True,'journal_unchanged':True,'supervisor_unchanged':True,'calibration_identity_unchanged':True},
   preserved_store={'path':str(STORE),'sha256':sha(STORE),'bytes':len(store),'crc32':crc(store),'must_match_before_and_after_firmware_boot':True},
   recovery={'image':str(SOURCE/(OLD+'.webformat.bin')),'sha256':sha(SOURCE/(OLD+'.webformat.bin')),'bytes':len(fallback),'version':source['product_version'],'kernel_build':'#358','full_slot_crc32_with_preserved_store':crc(fallback_prefix+store),'prefix_crc32':crc(fallback_prefix),'store_must_be_preserved':True},
   reproducibility={'components':str(a.components),'kernel_rebuilds':1,'sensor_and_qdrv_double_build':True,'rootfs_repacked_twice':True,'epoch':EPOCH},physical_validation={'status':'NOT_RUN','temperature_activation':'UNRUN','wifi_tests':'DEFERRED'},safety={'hardware_actions':False,'firmware_erase_end_exclusive':'0xdc0000','write_prefix_bytes':0x5e0000,'normal_write_target':'physical mtd4/linux_live at 0x7e0000','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],'startup_sensor_mmio':False,'startup_flash_writes':False,'flash_go_no_go':'OFFLINE_GO_PHYSICAL_INSTALLER_AND_TEMPERATURE_GATE_PENDING'})
  m['temperature']['helper_test']={'path':str(a.helper_test),'sha256':sha(a.helper_test)}
  m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved F361 sequence2 journal, not FF'}
  m['layout']['firmware_prefix_crc32']=crc(prefix)
  (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inventory,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f362',build/'known_hosts.f363')
  (build/'LAYOUT.md').write_text('# F363 temperature diagnostic\n\nF362 plus CONFIG_HWMON=m, explicit inactive temperature provider and guarded qdrv consumer. Kernel identity #358, F352 Ethernet and journal persistence preserved. No sensor MMIO until explicit enable. WPS signal offsets follow actual kernel ABI; no WPS activation. Root alone owns any physical action. Preserve existing journal and protected partitions.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in ('.webformat.bin','.rootfs.squashfs','.kernel.raw.bin','.kernel.lzma','.config','.dtb','.vmlinux'):assert sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix))
 assert (out/'a/rootfs-inventory.json').read_bytes()==(out/'b/rootfs-inventory.json').read_bytes()
 for p,digest in inputs.items():assert sha(p)==digest
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text());image=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f363-temperature-image/v1','status':'PASS_OFFLINE_TEMPERATURE_DIAGNOSTIC_IMAGE','artifact':{'path':str(image),'bytes':image.stat().st_size,'sha256':sha(image)},'manifest_sha256':sha(final/'manifest.json'),'product_version':VERSION,'firmware_build_id':build_id,'kernel_build':'#358','kernel_result':str(a.components),'reproducible_rootfs_and_image':True,'bootbase':'PASS','slot_fit':True,'prefix_crc32':m['layout']['firmware_prefix_crc32'],'full_slot':m['artifacts']['full_slot'],'preserved_store':m['preserved_store'],'rootfs_changed_files':m['change_scope']['files'],'default_sensor_mmio':False,'default_temperature_state':{'enabled':0,'activation_attempted':0,'activation_error':-19},'qdrv_comparisons':components['qdrv_comparisons'],'hardware_actions':False,'startup_flash_writes':False,'automatic_arm':False,'automatic_reboot':False,'recovery':m['recovery'],'flash_go_no_go':m['safety']['flash_go_no_go']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'result':str(out/'result.json')},indent=2))
if __name__=='__main__':main()
