"""Compose a reproducible full F340 baseline; never installs or arms hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,hashlib,io,json,shutil,subprocess
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f340_watchdog_rootfs_worker import PRODUCT_VERSION
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f321-f314-device-bound'
OLD='openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
BASE='openmitrastar-linux510-f340-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
EPOCH=1788566400
ROOTFS_OFFSET,ROOTFS_WINDOW,STORE_OFFSET,SLOT_BYTES=0x180000,0x460000,0x5e0000,0x7a0000
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--kernel-result',type=Path,required=True);ap.add_argument('--supervisor-result',type=Path,required=True);a=ap.parse_args()
 kernel=json.loads(a.kernel_result.read_text());supervisor=json.loads(a.supervisor_result.read_text())
 if kernel['status']!='PASS_OFFLINE_WATCHDOG_KERNEL_UNARMED' or supervisor['status']!='PASS_OFFLINE_SUPERVISOR':raise ValueError('unqualified inputs')
 for result in [kernel,supervisor]:
  if sha(result['artifact']['path'])!=result['artifact']['sha256']:raise ValueError('artifact drift')
 if sha(SOURCE/(OLD+'.webformat.bin'))!='eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18':raise ValueError('F321 drift')
 for name,digest in supervisor['sources'].items():
  if sha(ROOT/name)!=digest:raise ValueError('supervisor source drift')
 final=DEVICE/'firmware/f340-f321-watchdog-baseline-device-bound'
 if final.exists():raise ValueError('refusing existing F340 artifact')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f340-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={'kernel_result':sha(a.kernel_result),'supervisor_result':sha(a.supervisor_result),'worker':sha(ROOT/'tools/f340_watchdog_rootfs_worker.py'),'builder':sha(Path(__file__))}
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 source_manifest=json.loads((SOURCE/'manifest.json').read_text());kernel_dir=a.kernel_result.parent
 fields={'f340.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','f340.raw.bin':'kernel-squashfs.raw.bin','f340.lzma':'kernel-squashfs.lzma','f340.config':'kernel-squashfs.config','f340.dtb':'topaz_mitrastar_squashfs.dtb','f340.vmlinux':'kernel-squashfs.vmlinux'}
 for lane in ['a','b']:
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory_path=out/lane/'rootfs-inventory.json'
  for name,target in fields.items():shutil.copyfile(kernel_dir/lane/name,assets/target)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f340_watchdog_rootfs_worker.py'),
   '--source',linux(SOURCE/(OLD+'.rootfs.squashfs')),'--supervisor',linux(supervisor['artifact']['path']),'--supervisor-sha256',supervisor['artifact']['sha256'],
   '--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory_path)]
  worker=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=900)
  (out/lane/'worker.stdout').write_bytes(worker.stdout);(out/lane/'worker.stderr').write_bytes(worker.stderr)
  if worker.returncode:raise RuntimeError('F340 rootfs worker failed: '+worker.stderr.decode(errors='replace')[-1200:])
  settings={'ASSETS':assets,'OUT':build,'BASE':BASE,'ROOTFS_WINDOW':ROOTFS_WINDOW,'SOURCE_DATE_EPOCH':EPOCH};saved={k:getattr(compose,k) for k in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   for k,v in settings.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=SOURCE/(OLD+'.webformat.bin')
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   compose.f71.TEMPLATE=template
   for k,v in saved.items():setattr(compose,k,v)
  (out/lane/'composition.log').write_text(log.getvalue())
  if rc:raise ValueError('F340 composition failed')
  manifest=json.loads((build/'manifest.json').read_text());inventory=json.loads(inventory_path.read_text());image=build/(BASE+'.webformat.bin')
  if manifest['contracts']['bootbase']!='PASS' or image.stat().st_size>STORE_OFFSET:raise ValueError('Bootbase/store overlap')
  manifest.update(schema='openmitrastar.f340-watchdog-baseline/v1',classification='F321_BASELINE_WITH_INACTIVE_WATCHDOG_AND_EXPLICIT_SUPERVISOR',
   product_version=PRODUCT_VERSION,firmware_build_id=build_id,candidate_eligible=False,flash_supported=False,release_eligible=False,
   generated_at_utc=stamp,source={'firmware':'exact F321','image_sha256':sha(SOURCE/(OLD+'.webformat.bin')),'rootfs_sha256':sha(SOURCE/(OLD+'.rootfs.squashfs')),'device_queried':False},
   frontend=source_manifest['frontend'],device_identity=source_manifest['device_identity'],web_identity=source_manifest['web_identity'],web_security=source_manifest['web_security'],
   watchdog={'automatic_arm':False,'supervisor_auto_start':False,'default_driver_probe':'read-only/inactive-only','kernel_identity':'#340 / F340_WATCHDOG_BASELINE',
    'supervisor':supervisor['artifact'],'kernel_result':str(a.kernel_result),'kernel_result_sha256':sha(a.kernel_result),'supervisor_result_sha256':sha(a.supervisor_result),
    'session_max_ms':180000,'phase_max_ms':60000,'pet_interval_ms':1000,'driver_timeout_reported_seconds':8,'clock_physically_measured':False,
    'kernel_source':kernel['isolated_build']+'/linux','kernel_build_directory':(kernel_dir/lane/'build-directory.txt').read_text().strip(),
    'module_symvers':str(kernel_dir/lane/'Module.symvers'),'module_symvers_sha256':sha(kernel_dir/lane/'Module.symvers'),
    'arming_eligibility':'PENDING_ROOT_F336_PHYSICAL_QUALIFICATION','test_claim':'offline only'},
   change_scope={'rootfs':inventory['checks'],'kernel':'F329/F336 watchdog ownership and driver, new F340 identity; F321 radio/network/storage DT unchanged','radio_controls':'byte-identical F321','dfs_f338_included':False,'wps_f335_included':False,'sensor_f339_included':False},
   storage={**source_manifest['storage'],'persistent_writes_enabled':False},
   recovery={'image':str(SOURCE/(OLD+'.webformat.bin')),'sha256':sha(SOURCE/(OLD+'.webformat.bin')),'bytes':(SOURCE/(OLD+'.webformat.bin')).stat().st_size,
    'proven_last_restore':'outputs/recovery/f334-after-reset-20260921T120202Z-fd02977b/result.json','plan':'exact F321 mtd4 guarded restore; fresh protected/slot evidence required','mtd3_independent_recovery_proven':False},
   reproducibility={'independent_kernel_builds':True,'independent_rootfs_repack_and_composition':True,'epoch':EPOCH,'inputs':inputs},
   physical_validation={'status':'NOT_RUN','watchdog_armed':False,'wifi_client_tests':'DEFERRED_BY_OWNER'},
   safety={'hardware_actions':False,'normal_write_target':'physical mtd4/linux_live only with applicable gates','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],'mtd6':'logical view, never physical write','flash_go_no_go':'NO_GO_PHYSICAL_QUALIFICATION_AND_EXECUTOR_PENDING'})
  manifest['layout']['mtd_mapping']='F321 read-only MTD views retained; rootfs physical 0x90960000+0x460000, store 0x90dc0000+0x1c0000'
  (build/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
  shutil.copyfile(inventory_path,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f321',build/'known_hosts.f340')
  (build/'LAYOUT.md').write_text('# F340 watchdog baseline\n\nF321 radio/UI/calibration preserved; watchdog registers inactive; supervisor requires an explicit ARM. No automatic arm or supervisor init service. No F338 DFS, F335 WPS or F339 sensor changes.\n\nFull firmware image for physical mtd4 only after separate qualification; never install the intermediate kernel-only RAS. Exact F321 is the rollback.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in ['.webformat.bin','.rootfs.squashfs','.kernel.raw.bin','.kernel.lzma','.dtb','.config','.vmlinux']:
  if sha(out/'a/build'/(BASE+suffix))!=sha(out/'b/build'/(BASE+suffix)):raise ValueError('reproduction mismatch '+suffix)
 if (out/'a/rootfs-inventory.json').read_bytes()!=(out/'b/rootfs-inventory.json').read_bytes():raise ValueError('rootfs inventory reproduction mismatch')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 manifest=json.loads((final/'manifest.json').read_text());image=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f340-fullimage-build/v1','status':'PASS_OFFLINE_REPRODUCIBLE_FULL_IMAGE_UNARMED','artifact':{'path':str(image),'bytes':image.stat().st_size,'sha256':sha(image)},
  'output':str(final),'manifest_sha256':sha(final/'manifest.json'),'full_slot':manifest['artifacts']['full_slot'],'reproducible':True,'bootbase':'PASS','slot_fit':True,
  'watchdog_automatic_arm':False,'hardware_actions':False,'kernel_result':str(a.kernel_result),'supervisor_result':str(a.supervisor_result),'firmware_build_id':build_id}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'result':str(out/'result.json')},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
