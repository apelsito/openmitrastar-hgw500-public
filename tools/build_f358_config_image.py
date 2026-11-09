"""Compose full private F358 from F340 and qualified inactive components. No hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,hashlib,io,json,shutil,subprocess
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f358_config_rootfs_worker import PRODUCT_VERSION
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f340-f321-watchdog-baseline-device-bound'
OLD='openmitrastar-linux510-f340-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
BASE='openmitrastar-linux510-f358-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
BUNDLE=ROOT/'outputs/kernel-port/f356-observe-ram-20260921T171309Z'
KERNEL=DEVICE/'analysis/f350-flash-arbitration-20260921T155949Z'
EPOCH=1790006400
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 global KERNEL
 ap=argparse.ArgumentParser();ap.add_argument('--kernel-result',type=Path,required=True);ap.add_argument('--supervisor-result',type=Path,required=True);args=ap.parse_args()
 KERNEL=args.kernel_result.resolve().parent;kr=json.loads(args.kernel_result.read_text());sr=json.loads(args.supervisor_result.read_text())
 if kr['kernel_build_identity']!=358 or kr['status'] not in ('PASS_OFFLINE_KERNEL_SINGLE_BUILD','PASS_OFFLINE_READER_ARBITRATION_KERNEL') or sr['status']!='PASS_OFFLINE_SUPERVISOR_PROFILE':raise ValueError('unqualified F358 inputs')
 for value in kr['artifacts'].values():
  if sha(value['path'])!=value['sha256']:raise ValueError('kernel input drift')
 if sha(sr['artifact']['path'])!=sr['artifact']['sha256']:raise ValueError('supervisor input drift')
 if shutil.disk_usage('C:/').free<=500*1024*1024:raise ValueError('C disk floor')
 if sha(BUNDLE/'result.json')!='5ae7ad32f718da536787cb1008450a24ce4551861245ca3c64a5ebcf89fe7d0f':raise ValueError('F356 bundle drift')
 bundle=json.loads((BUNDLE/'result.json').read_text());source=json.loads((SOURCE/'manifest.json').read_text())
 if sha(SOURCE/(OLD+'.webformat.bin'))!='211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa':raise ValueError('F340 image drift')
 for name in ['provider','supervisor_ram','cli']:
  p=bundle[name]
  if sha(p['path'])!=p['sha256']:raise ValueError('component drift '+name)
 bundle['supervisor_ram']=sr['artifact']
 old_exports=set((DEVICE/'analysis/f340-watchdog-kernel-20260921T132951Z/a/Module.symvers').read_text().splitlines())
 new_exports=set((KERNEL/'a/Module.symvers').read_text().splitlines())
 if not old_exports<=new_exports:raise ValueError('F340 exported ABI changed')
 provider=json.loads((ROOT/bundle['evidence']['provider']['path']).read_text());available={line.split()[1] for line in new_exports}
 if not set(provider['imports'])<=available:raise ValueError('provider-kernel imports unresolved')
 final=DEVICE/'firmware/f358-f340-config-backend-device-bound'
 if final.exists():raise ValueError('immutable F358 already exists')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f358-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f358_config_rootfs_worker.py',BUNDLE/'result.json',SOURCE/'manifest.json',args.kernel_result,args.supervisor_result]}
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 assets_map={'f358.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','f358.raw.bin':'kernel-squashfs.raw.bin','f358.config':'kernel-squashfs.config','f358.dtb':'topaz_mitrastar_squashfs.dtb','f358.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 compressor=ROOT/'work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma'
 if sha(compressor)!='04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18':raise ValueError('compressor drift')
 compressed=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e',linux(compressor),'--keep','--best',linux(KERNEL/'a/f358.raw.bin'),'-c'],capture_output=True,check=True)
 (out/'kernel.lzma').write_bytes(compressed.stdout)
 for lane in ['a','b']:
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory_path=out/lane/'rootfs-inventory.json'
  for name,target in assets_map.items():shutil.copyfile(KERNEL/'a'/name,assets/target)
  shutil.copyfile(out/'kernel.lzma',assets/'kernel-squashfs.lzma')
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f358_config_rootfs_worker.py'),'--source',linux(SOURCE/(OLD+'.rootfs.squashfs')),'--provider',linux(bundle['provider']['path']),'--supervisor',linux(bundle['supervisor_ram']['path']),'--cli',linux(bundle['cli']['path']),'--supervisor-sha256',bundle['supervisor_ram']['sha256'],'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory_path)]
  worker=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=900)
  (out/lane/'worker.stdout').write_bytes(worker.stdout);(out/lane/'worker.stderr').write_bytes(worker.stderr)
  if worker.returncode:raise RuntimeError('F358 rootfs worker: '+worker.stderr.decode(errors='replace')[-1200:])
  settings={'ASSETS':assets,'OUT':build,'BASE':BASE,'ROOTFS_WINDOW':0x460000,'SOURCE_DATE_EPOCH':EPOCH};saved={k:getattr(compose,k) for k in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   for k,v in settings.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=SOURCE/(OLD+'.webformat.bin')
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   compose.f71.TEMPLATE=template
   for k,v in saved.items():setattr(compose,k,v)
  (out/lane/'composition.log').write_text(log.getvalue())
  if rc:raise ValueError('composition failed')
  manifest=json.loads((build/'manifest.json').read_text());inventory=json.loads(inventory_path.read_text());image=build/(BASE+'.webformat.bin')
  if manifest['contracts']['bootbase']!='PASS' or image.stat().st_size>0x5e0000:raise ValueError('Bootbase/store overlap')
  if (build/(BASE+'.kernel.raw.bin')).read_bytes()!=(KERNEL/'a/f358.raw.bin').read_bytes():raise ValueError('kernel changed')
  manifest.update(schema='openmitrastar.f358-config-backend/v1',classification='F340_WITH_CONFIG_BACKEND_AVAILABLE_INACTIVE',product_version=PRODUCT_VERSION,firmware_build_id=build_id,generated_at_utc=stamp,
   candidate_eligible=False,flash_supported=False,release_eligible=False,
   source={'firmware':'exact private F340','image_sha256':sha(SOURCE/(OLD+'.webformat.bin')),'rootfs_sha256':sha(SOURCE/(OLD+'.rootfs.squashfs')),'device_queried':False,'bundle':str(BUNDLE/'result.json'),'bundle_sha256':sha(BUNDLE/'result.json')},
   frontend=source['frontend'],device_identity=source['device_identity'],web_identity=source['web_identity'],web_security=source['web_security'],
   change_scope={'rootfs':inventory['checks'],'files':inventory['changed_files'],'kernel':'F358 map resource fix only; config/DT unchanged','original_radios_init_calibration_identity':'byte-identical F340','wifi_changes':False,'f355_included':False},
   config_backend={'available':True,'autoload':False,'startup_mmio':False,'automatic_writes':False,'module':'/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn_f356_journal.ko','module_sha256':bundle['provider']['sha256'],'cli':'/usr/sbin/om-journal-cli','cli_sha256':bundle['cli']['sha256'],'default_allow_hw':False,'default_allow_program':False,'activation':'explicit separate campaign','payload_max':4096},
   watchdog={'automatic_arm':False,'supervisor_auto_start':False,'supervisor_sha256':bundle['supervisor_ram']['sha256'],'kernel_identity':'#358 @1790006400 / F340_WATCHDOG_BASELINE','ipc_schema':'openmitrastar.f340-supervisor-state/v1','sysfs':'f340','kernel_manifest':str(args.kernel_result)},
   module_closure={'all_f340_exports_preserved':True,'provider_imports_resolved':True,'original_modules_unchanged':True,'kernel_module_symvers_sha256':sha(KERNEL/'a/Module.symvers')},
   storage={**source['storage'],'persistent_writes_enabled_by_default':False,'journal_activation':'explicit only'},
   recovery={'image':str(SOURCE/(OLD+'.webformat.bin')),'sha256':sha(SOURCE/(OLD+'.webformat.bin')),'bytes':(SOURCE/(OLD+'.webformat.bin')).stat().st_size,'version':source['product_version'],'plan':'exact F340 guarded restore, preserve store, fresh protected/slot evidence','mtd3_independent_recovery_proven':False},
   reproducibility={'kernel_recompiled_in_composer':False,'kernel_reproducible':bool(kr['reproducible']),'independent_rootfs_repack_and_composition':True,'epoch':EPOCH,'inputs':inputs},physical_validation={'status':'NOT_RUN','watchdog_armed':False,'backend_loaded':False,'wifi_client_tests':'DEFERRED_BY_OWNER'},
   safety={'hardware_actions':False,'normal_write_target':'physical mtd4/linux_live only with separate gates','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],'mtd6':'logical view, never physical write','flash_go_no_go':'NO_GO_ROOT_OBSERVATION_AND_EXECUTOR_REVIEW_PENDING','full_slot_crc_is_reference_padding_not_future_mutable_store':True})
  (build/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
  shutil.copyfile(inventory_path,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f340',build/'known_hosts.f358')
  (build/'LAYOUT.md').write_text('# F358 inactive configuration backend\n\nFull persistent image, corrected F358 kernel and F340 radios/rootfs except eight declared files. No module autoload, MMIO, watchdog ARM or storage write at boot. Explicit campaign activation only; exact F340 fallback. Only mtd4 firmware prefix may be installed after separate root gates. Preserve mutable store.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in ['.webformat.bin','.rootfs.squashfs','.kernel.raw.bin','.kernel.lzma','.dtb','.config','.vmlinux']:
  if sha(out/'a/build'/(BASE+suffix))!=sha(out/'b/build'/(BASE+suffix)):raise ValueError('reproduction mismatch '+suffix)
 if (out/'a/rootfs-inventory.json').read_bytes()!=(out/'b/rootfs-inventory.json').read_bytes():raise ValueError('rootfs delta mismatch')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 manifest=json.loads((final/'manifest.json').read_text());image=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f358-fullimage-build/v1','status':'PASS_OFFLINE_FULL_IMAGE_BACKEND_INACTIVE','artifact':{'path':str(image),'bytes':image.stat().st_size,'sha256':sha(image)},'manifest_sha256':sha(final/'manifest.json'),'output':str(final),'product_version':PRODUCT_VERSION,'firmware_build_id':build_id,'full_slot':manifest['artifacts']['full_slot'],'reproducible':True,'bootbase':'PASS','slot_fit':True,'rootfs_changed_files':manifest['change_scope']['files'],'kernel_recompiled':False,'backend_autoload':False,'startup_mmio_or_writes':False,'watchdog_automatic_arm':False,'hardware_actions':False,'fallback':manifest['recovery']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'result':str(out/'result.json')},indent=2))
if __name__=='__main__':main()
