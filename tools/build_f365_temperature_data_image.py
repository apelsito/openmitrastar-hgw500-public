"""Compose F365 cached temperature diagnostics on exact F364r3; no hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess,zlib
from elftools.elf.elffile import ELFFile
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f365_rootfs_worker import VERSION,SENSOR
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
BASE='openmitrastar-linux510-f365-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
EPOCH=1790006400

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def crc(b):return f'{zlib.crc32(b)&0xffffffff:08x}'
def require(v,m):
 if not v:raise ValueError(m)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--f364r3-image-result',type=Path,required=True)
 ap.add_argument('--sensor-result',type=Path,required=True);args=ap.parse_args()
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 image_proof=json.loads(args.f364r3_image_result.read_text());sensor=json.loads(args.sensor_result.read_text())
 require(sha(args.f364r3_image_result)=='2427375c5b5bae466dc4d377e7d0d4ca9ed18e03c996942eb5c205cc805c969a','exact F364r3 result required')
 require(image_proof['schema']=='openmitrastar.f364r3-lifetime-image/v1' and image_proof['status']=='PASS_OFFLINE_LIFETIME_START_HASH_FIXED_IMAGE','F364r3 image acceptance')
 require(sensor['schema']=='openmitrastar.f365-temperature-diagnostic-module/v1' and sensor['status']=='PASS_OFFLINE_CACHED_DATA_DIAGNOSTIC_MODULE','real F365 module PASS required')
 require(sensor['reproducible'] is True and sensor['module_version']=='363' and sensor['diagnostic_revision']=='365','sensor profile/reproduction')
 require(sensor['f364r3_image_result']['sha256']==sha(args.f364r3_image_result),'module compiled for different baseline')
 for p,h in sensor['source_pins'].items():require(sha(p)==h,'F365 module source drift')
 test=sensor['tests'];require(sha(test['path'])==test['sha256'],'F365 bank evidence drift')
 test_record=json.loads(Path(test['path']).read_text());require(test_record['status']==test['status'] and test['status'].startswith('PASS'),'F365 bank not accepted')
 module=Path(sensor['artifact']['path']);require(module.stat().st_size==sensor['artifact']['bytes'] and sha(module)==sensor['artifact']['sha256'],'sensor artifact binding')
 with module.open('rb') as f:
  elf=ELFFile(f);info=dict(row.split('=',1) for row in elf.get_section_by_name('.modinfo').data().decode().split('\0') if '=' in row)
 require(info.get('name')=='temp_sens' and info.get('version')=='363' and info.get('diagnostic_revision')=='365','module admission identity')
 image_path=Path(image_proof['artifact']['path']);source_dir=image_path.parent;old=image_path.name.removesuffix('.webformat.bin')
 require(sha(image_path)=='ee6b7d09fd9e2dc5e0009d6756910510409ae13fb17108089a4caf7043056a15','F364r3 image drift')
 require(sha(source_dir/'manifest.json')=='45050fbc20981c6e76115acd01bd3e7a5e0138dcd24605b0624ec37a7fb1899d','F364r3 manifest drift')
 source=json.loads((source_dir/'manifest.json').read_text());inventory=json.loads((source_dir/'rootfs-inventory.json').read_text())
 old_sensor_sha=inventory['after'][SENSOR]['sha256'];require(old_sensor_sha==source['temperature']['sensor_module']['sha256'],'source sensor binding')
 require(sensor['f339_core_sha256']==source['temperature']['core_sha256'],'sensor core/table changed')
 store_spec=source['preserved_store'];store=Path(store_spec['path']).read_bytes()
 require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'store binding')
 fallback=image_path.read_bytes();fallback_prefix=fallback+b'\xff'*(0x5e0000-len(fallback));fallback_full=fallback_prefix+store
 require(crc(fallback_full)==source['artifacts']['full_slot']['crc32'],'source full slot/store mismatch')
 final=DEVICE/'firmware/f365-f364r3-temperature-data-device-bound';require(not final.exists(),'immutable F365 image exists')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f365-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f365_rootfs_worker.py',args.f364r3_image_result,args.sensor_result,source_dir/'manifest.json',Path(test['path']),Path(store_spec['path'])]}
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 fields={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps({'build_started':str(out),'source_firmware':'F364r3','hardware_actions':False}),flush=True)
 for lane in ('a','b'):
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inv=out/lane/'rootfs-inventory.json'
  for suffix,name in fields.items():shutil.copyfile(source_dir/(old+suffix),assets/name)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f365_rootfs_worker.py'),
        '--source',linux(source_dir/(old+'.rootfs.squashfs')),'--source-sha',source['artifacts']['rootfs_squashfs']['sha256'],
        '--base-module-sha',old_sensor_sha,'--module',linux(module),'--module-sha',sensor['artifact']['sha256'],
        '--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inv)]
  run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr)
  require(run.returncode==0,run.stderr.decode(errors='replace')[-1500:])
  settings={'ASSETS':assets,'OUT':build,'BASE':BASE,'ROOTFS_WINDOW':0x460000,'SOURCE_DATE_EPOCH':EPOCH};saved={k:getattr(compose,k) for k in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   for k,v in settings.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=image_path
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   compose.f71.TEMPLATE=template
   for k,v in saved.items():setattr(compose,k,v)
  (out/lane/'composition.log').write_text(log.getvalue());require(rc==0,'composition failed')
  composed=json.loads((build/'manifest.json').read_text());delta=json.loads(inv.read_text());candidate=build/(BASE+'.webformat.bin');body=candidate.read_bytes()
  require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS','Bootbase/store overlap')
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store;m=copy.deepcopy(source)
  for key in ('layout','kernel','rootfs','artifacts','contracts'):m[key]=composed[key]
  m.update(schema='openmitrastar.f365-temperature-data-image/v1',classification='F364R3_WITH_CACHED_TEMPERATURE_DATA_DIAGNOSTICS',
   product_version=VERSION,firmware_build_id=build_id,generated_at_utc=stamp,candidate_eligible=True,flash_supported=False,release_eligible=False,
   source={'firmware':'F364r3 exact','image_sha256':sha(image_path),'manifest_sha256':sha(source_dir/'manifest.json'),'inputs':inputs},
   change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'kernel_config_dt_qdrv_unchanged':True,
                'provider_preload_and_radio_dirty_gate_unchanged':True,'helper_existing_actions_unchanged':True,
                'diagnostic_helper_action':'two cached JSON lines from diag_hwmon/diag_legacy','automatic_sensor_activation':False,
                'f339_core_table_start_timeout_unchanged':True,'additional_sensor_mmio_reads':False,
                'ethernet_identity_journal_watchdog_unchanged':True},
   preserved_store=store_spec,
   recovery={'image':str(image_path),'sha256':sha(image_path),'bytes':len(fallback),'version':source['product_version'],
             'kernel_build':'#358','prefix_crc32':crc(fallback_prefix),'full_slot_crc32_with_preserved_store':crc(fallback_full),
             'store_must_be_preserved':True,'physical_baseline_and_recovery_acceptance':'root installer selects accepted physical baseline'},
   reproducibility={'kernel_or_qdrv_recompiled':False,'sensor_double_build_reused':True,'rootfs_repacked_twice':True,'epoch':EPOCH},
   physical_validation={'status':'NOT_RUN','temperature_diagnostic_capture':'UNRUN','radio_rf_client_tests':'DEFERRED'},
   safety={'hardware_actions':False,'write_prefix_bytes':0x5e0000,'firmware_erase_end_exclusive':'0xdc0000',
           'normal_write_target':'physical mtd4/linux_live at 0x7e0000','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],
           'startup_sensor_mmio':False,'startup_flash_writes':False,'automatic_arm':False,'automatic_reboot':False,
           'flash_go_no_go':'OFFLINE_GO_PHYSICAL_INSTALLER_AND_DIAGNOSTIC_GATE_PENDING'})
  m['temperature'].update(sensor_module={'path':str(module),'runtime_path':'/'+SENSOR,'sha256':sha(module),'bytes':module.stat().st_size},
   module_version='363',diagnostic_revision='365',diagnostic_module_result={'path':str(args.sensor_result),'sha256':sha(args.sensor_result)},
   diagnostics={'command':'om-temperature-f363 diagnostics','schema':'openmitrastar.f365-temperature-access/v1',
                'streams':['hwmon','legacy'],'attributes':['diag_hwmon','diag_legacy'],'cached_ram_only':True,'additional_sensor_reads':False},
   default_sensor_mmio=False,default_enabled=False)
  m['module_closure']['temperature_diagnostic_module']={'path':str(args.sensor_result),'sha256':sha(args.sensor_result)}
  m['layout']['firmware_prefix_crc32']=crc(prefix)
  m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, not FF padding'}
  (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inv,build/'rootfs-inventory.json')
  shutil.copyfile(source_dir/'known_hosts.f364',build/'known_hosts.f365')
  (build/'LAYOUT.md').write_text('# F365 cached temperature DATA diagnostics\n\nExact F364r3 kernel/DT/config/qdrv and provider admission remain unchanged. Sensor records only existing reads in separate hwmon/legacy caches. Helper diagnostics reads cached RAM; it neither enables the sensor nor starts a sample. F339 core/table/start/timeout unchanged. Physical diagnostics and image installation remain separate root gates. Preserve journal and protected partitions.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in (*fields,'.rootfs.squashfs','.webformat.bin'):require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
 for p,h in inputs.items():require(sha(p)==h,'composition input changed')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text());candidate=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f365-temperature-data-image/v1','status':'PASS_OFFLINE_CACHED_TEMPERATURE_DATA_IMAGE',
  'artifact':{'path':str(candidate),'bytes':candidate.stat().st_size,'sha256':sha(candidate)},'manifest_sha256':sha(final/'manifest.json'),
  'product_version':VERSION,'firmware_build_id':build_id,'source_image_result':str(args.f364r3_image_result),'sensor_result':str(args.sensor_result),
  'kernel_config_dt_qdrv_unchanged':True,'provider_preload_gate_unchanged':True,'helper_existing_actions_unchanged':True,
  'automatic_sensor_activation':False,'reproducible':True,'bootbase':'PASS','slot_fit':True,
  'prefix_crc32':m['layout']['firmware_prefix_crc32'],'full_slot':m['artifacts']['full_slot'],'preserved_store':store_spec,
  'rootfs_changed_files':m['change_scope']['files'],'hardware_actions':False,'recovery':m['recovery'],'flash_go_no_go':m['safety']['flash_go_no_go']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'result':str(out/'result.json')},indent=2))
if __name__=='__main__':main()
