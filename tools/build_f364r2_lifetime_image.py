"""Compose F364 only from a completed real F363 image and qualified lifetime qdrv."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess,zlib
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f364r2_rootfs_worker import VERSION
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
BASE='openmitrastar-linux510-f364r2-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
EPOCH=1790006400

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def crc(b):return f'{zlib.crc32(b)&0xffffffff:08x}'
def require(v,m):
 if not v:raise ValueError(m)

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--f363-image-result',type=Path,required=True)
 ap.add_argument('--lifetime-result',type=Path,required=True);args=ap.parse_args()
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 image_proof=json.loads(args.f363_image_result.read_text());life=json.loads(args.lifetime_result.read_text())
 require(image_proof['schema']=='openmitrastar.f363-temperature-image/v1' and image_proof['status']=='PASS_OFFLINE_TEMPERATURE_DIAGNOSTIC_IMAGE','completed real F363 image required')
 require(life['status']=='PASS_OFFLINE_F363_PLUS_F355_LIFETIME' and life['reproducible'],'qualified F364 lifetime required')
 image_path=Path(image_proof['artifact']['path']);source_dir=image_path.parent;old=image_path.name.removesuffix('.webformat.bin')
 require('f363' in old and sha(image_path)==image_proof['artifact']['sha256'] and image_path.stat().st_size==image_proof['artifact']['bytes'],'F363 artifact binding')
 require(sha(source_dir/'manifest.json')==image_proof['manifest_sha256'],'F363 manifest binding')
 source=json.loads((source_dir/'manifest.json').read_text());kr_path=Path(life['f363_components']['path'])
 require(sha(kr_path)==life['f363_components']['sha256'],'F363 kernel component binding')
 kr=json.loads(kr_path.read_text());require(kr['status']=='PASS_OFFLINE_TEMPERATURE_INTEGRATION','F363 component acceptance')
 for sidecar,name in (('.config','f363.config'),('.dtb','f363.dtb'),('.vmlinux','f363.vmlinux')):
  require(sha(source_dir/(old+sidecar))==kr['artifacts'][name]['sha256'],'F363 kernel profile mismatch '+name)
 require(sha(life['artifact']['path'])==life['artifact']['sha256'],'lifetime module drift')
 store_spec=image_proof['preserved_store'];store=Path(store_spec['path']).read_bytes()
 require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'preserved store binding')
 fallback=image_path.read_bytes();fallback_prefix=fallback+b'\xff'*(0x5e0000-len(fallback));fallback_full=fallback_prefix+store
 require(crc(fallback_full)==source['artifacts']['full_slot']['crc32'],'F363 full slot with real store')
 final=DEVICE/'firmware/f364r2-f363-lifetime-device-bound';require(not final.exists(),'immutable F364 exists')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f364r2-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f364r2_rootfs_worker.py',args.f363_image_result,args.lifetime_result,source_dir/'manifest.json',kr_path,Path(store_spec['path'])]}
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 fields={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps({'build_started':str(out),'source_firmware':'F363','hardware_actions':False}),flush=True)
 for lane in ('a','b'):
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory=out/lane/'rootfs-inventory.json'
  for suffix,name in fields.items():shutil.copyfile(source_dir/(old+suffix),assets/name)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f364r2_rootfs_worker.py'),
        '--source',linux(source_dir/(old+'.rootfs.squashfs')),'--source-sha',source['artifacts']['rootfs_squashfs']['sha256'],
        '--base-qdrv-sha',kr['artifacts']['a/temperature/qdrv/qdrv.ko']['sha256'],
        '--module',linux(life['artifact']['path']),'--module-sha',life['artifact']['sha256'],
        '--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
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
  composed=json.loads((build/'manifest.json').read_text());delta=json.loads(inventory.read_text());candidate=build/(BASE+'.webformat.bin');body=candidate.read_bytes()
  require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS','Bootbase or store overlap')
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store
  m=copy.deepcopy(source)
  for key in ('layout','kernel','rootfs','artifacts','contracts'):m[key]=composed[key]
  m.update(schema='openmitrastar.f364r2-lifetime-image/v1',classification='F363_WITH_QUALIFIED_F355_LIFETIME_ONLY',product_version=VERSION,
   firmware_build_id=build_id,generated_at_utc=stamp,candidate_eligible=True,flash_supported=False,release_eligible=False,
   source={'firmware':'F363 exact complete temperature image','image_sha256':sha(image_path),'manifest_sha256':sha(source_dir/'manifest.json'),'inputs':inputs},
   change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'kernel_config_dt':'byte-identical F363',
                'thermal_guard_and_wps_layout':'compiled equivalence to F363 confirmed','temperature_sensor_and_consumers_retained':True,
                'radio_stop_helper_unchanged':True,'radio_start_change':'one qdrv hash literal corrected',
                'qdrv_hash_bindings':delta['qdrv_hash_bindings'],'stale_qdrv_hash_bindings':delta['stale_qdrv_hash_bindings'],'ethernet_identity_config_watchdog_unchanged':True,'inherited_f363_changes':source.get('change_scope')},
   lifetime={'component_result':str(args.lifetime_result),'component_sha256':sha(args.lifetime_result),'qdrv_sha256':life['artifact']['sha256'],
             'mechanism':'qualified F355 retained module reference after first admitted mutation; pre-init/failed-state admission guards',
             'status_sysfs':'/sys/devices/qdrv/lifetime_state','release_supported':False,'hot_restart_supported':False,
             'first_mutation_reboot_required_for_unload':True,'new_modes_or_dfs_implementation_added':False},
   preserved_store=store_spec,
   recovery={'image':str(image_path),'sha256':sha(image_path),'bytes':len(fallback),'version':source['product_version'],
             'kernel_build':'#358','prefix_crc32':crc(fallback_prefix),'full_slot_crc32_with_preserved_store':crc(fallback_full),
             'store_must_be_preserved':True,'physical_baseline_and_recovery_acceptance':'installer must select actual accepted baseline'},
   reproducibility={'kernel_recompiled':False,'qdrv_built_twice':True,'rootfs_repacked_twice':True,'epoch':EPOCH},
   physical_validation={'status':'NOT_RUN','radio_rf_client_tests':'DEFERRED','stop_unload_hardware_epoch':'NOT_PROVEN'},
   safety={'hardware_actions':False,'write_prefix_bytes':0x5e0000,'firmware_erase_end_exclusive':'0xdc0000',
           'normal_write_target':'physical mtd4/linux_live at 0x7e0000','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],
           'startup_flash_writes':False,'automatic_arm':False,'automatic_reboot':False,
           'flash_go_no_go':'OFFLINE_GO_PHYSICAL_INSTALLER_AND_RECOVERY_GATE_PENDING'})
  m['layout']['firmware_prefix_crc32']=crc(prefix)
  m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, not FF padding'}
  m['correction']={'rejected_f364_image_sha256':'1e2d07de0aaee45295b7cd27e5418898d7ceeaa7a2e4060391f0695092da2857','defect':'stale hardcoded qdrv hash in om-radio5-start','fixed_literal_old':delta['qdrv_literal_old'],'fixed_literal_new':delta['qdrv_literal_new']}
  m.setdefault('module_closure',{}).update(qdrv_lifetime_component=str(args.lifetime_result),qdrv_imports_resolved=life['imports_resolved'],qdrv_exports_unchanged=True,f355_included=True)
  (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inventory,build/'rootfs-inventory.json')
  shutil.copyfile(source_dir/'known_hosts.f363',build/'known_hosts.f364')
  (build/'LAYOUT.md').write_text('# F364r2 lifetime integration\n\nExact F363 kernel, temperature integration and WPS layout retained. qdrv, its one startup hash literal and catalogue/version metadata change. F355 retains module/resources after admitted mutation; no hot restart or release epoch is claimed. Preserve real journal and protected partitions. Physical installation and recovery remain separate root gates.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in (*fields,'.rootfs.squashfs','.webformat.bin'):require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
 for p,h in inputs.items():require(sha(p)==h,'input changed during composition')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text());candidate=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f364r2-lifetime-image/v1','status':'PASS_OFFLINE_LIFETIME_START_HASH_FIXED_IMAGE',
  'artifact':{'path':str(candidate),'bytes':candidate.stat().st_size,'sha256':sha(candidate)},'manifest_sha256':sha(final/'manifest.json'),
  'product_version':VERSION,'firmware_build_id':build_id,'f363_image_result':str(args.f363_image_result),'lifetime_result':str(args.lifetime_result),
  'kernel_result':str(kr_path),'kernel_config_dt_byte_identical_f363':True,'reproducible':True,'bootbase':'PASS','slot_fit':True,
  'prefix_crc32':m['layout']['firmware_prefix_crc32'],'full_slot':m['artifacts']['full_slot'],'preserved_store':store_spec,
  'rootfs_changed_files':m['change_scope']['files'],'correction':m['correction'],'qdrv_hash_bindings':m['change_scope']['qdrv_hash_bindings'],'hardware_actions':False,'recovery':m['recovery'],'flash_go_no_go':m['safety']['flash_go_no_go']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'result':str(out/'result.json')},indent=2))
if __name__=='__main__':main()
