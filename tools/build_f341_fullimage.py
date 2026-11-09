"""Compose F341 twice from F340 + exact coherent closure, without hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,hashlib,io,json,shlex,shutil,subprocess,tempfile
import compose_f164_squashfs_product as compose
from build_f321_classic_ui_candidate import KERNEL_FILES,ROOTFS_WINDOW,SLOT_BYTES,STORE_OFFSET,wsl_path
from init_lyoko_device_host_key import restrict_acl
from lyoko_web_rootfs_worker import sha256
from f341_runtime_contract import PRODUCT_VERSION
from f341_runtime_contract import native_start
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware'
BASE='openmitrastar-linux510-f341-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
VERSION=ROOT/'versions/lyoko-foundation-6.10.1-f341-native-diagnostic'
EPOCH=1790006400
def require(condition,message):
 if not condition:raise ValueError(message)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--f340-manifest',type=Path,required=True);ap.add_argument('--closure-manifest',type=Path,required=True);ap.add_argument('--distro',default='podman-mem9-tidb');a=ap.parse_args()
 source=json.loads(a.f340_manifest.read_text());closure=json.loads(a.closure_manifest.read_text())
 require(closure['status']=='PASS_F341_COHERENT_CLOSURE','F341 closure not qualified')
 require(source['contracts']['bootbase']=='PASS','F340 Bootbase contract not qualified')
 require(source['artifacts']['config']['sha256']==closure['kernel_config_sha256'],'kernel/module ABI mismatch')
 source_dir=a.f340_manifest.parent;source_image=source_dir/source['artifacts']['webformat']['file'];source_rootfs=source_dir/source['artifacts']['rootfs_squashfs']['file'];source_base=source_image.name.removesuffix('.webformat.bin')
 require(sha256(source_image)==source['artifacts']['webformat']['sha256'],'source F340 image drift');require(sha256(source_rootfs)==source['artifacts']['rootfs_squashfs']['sha256'],'source F340 rootfs drift')
 require(source_image.read_bytes()[0x180000:]==source_rootfs.read_bytes(),'source F340 image/rootfs inconsistency')
 require(sha256(source_dir/(source_base+'.vmlinux'))==closure['kernel_vmlinux_sha256'],'closure compiled against another kernel')
 final=DEVICE/'f341-f340-native-diagnostic-device-bound';require(not final.exists(),'refusing to replace an existing F341 candidate')
 overlay=VERSION/'overlay';helpers={p.relative_to(overlay).as_posix():sha256(p) for p in sorted(overlay.rglob('*')) if p.is_file()}
 runtime_path=ROOT/'outputs/preflight/f341-runtime-20260921T134922Z/result.json'
 ipc_path=ROOT/'outputs/preflight/f341-ipc-20260921T133749Z/result.json'
 control_path=ROOT/'outputs/preflight/f341-control-20260921T135050Z/result.json'
 supervisor_ipc_path=ROOT/'outputs/preflight/f341-f340-ipc-20260921T134922Z/result.json'
 runtime=json.loads(runtime_path.read_text());ipc=json.loads(ipc_path.read_text());control=json.loads(control_path.read_text());supervisor_ipc=json.loads(supervisor_ipc_path.read_text())
 require(runtime['status']=='PASS_OFFLINE_RUNTIME_TRANSITIONS' and ipc['status']=='PASS_ACTUAL_C_IPC_THREADS' and control['status']=='PASS_ACTUAL_F341_CONTROL' and supervisor_ipc['status']=='PASS_F341_F340_ACTUAL_IPC','F341 offline tests not qualified')
 for path,digest in runtime['sources'].items():require(sha256(overlay/path)==digest,'runtime helper changed after tests '+path)
 require(hashlib.sha256(native_start((ROOT/'versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start').read_bytes())).hexdigest()==runtime['native_sha256'],'native ladder changed after tests')
 require(closure['source']['provider\\f332_provider.c']==control['provider_sha256'],'control module/test source mismatch')
 require(closure['source']['provider\\f338_ipc.c']==ipc['source_sha256'],'IPC module/test source mismatch')
 wdt_path=ROOT/'outputs/handoff-live/f336-ram-20260921T133950Z-51c6016b/result.json';wdt=json.loads(wdt_path.read_text())
 require(wdt['status']=='CESSATION_RESET_AND_F321_RETURN_OBSERVED' and wdt['containment_confirmed'] and wdt['flash_crc_before']==wdt['flash_crc_after'],'first watchdog cessation gate unavailable')
 tools={name:sha256(ROOT/'tools'/name) for name in ('build_f341_fullimage.py','f341_rootfs_worker.py','f341_runtime_contract.py')}
 build_id=hashlib.sha256(json.dumps({'source':sha256(source_image),'closure':sha256(a.closure_manifest),'helpers':helpers,'tools':tools,'epoch':EPOCH},sort_keys=True).encode()).hexdigest()[:16]
 scratch_root=DEVICE/'.build-scratch';scratch_root.mkdir(exist_ok=True);restrict_acl(scratch_root,directory=True)
 scratch=Path(tempfile.mkdtemp(prefix='f341-native-',dir=scratch_root)).resolve();restrict_acl(scratch,directory=True)
 try:
  lane_results=[]
  module_dir=Path(closure['modules']['qtn_radar_f341']['path']).parent
  for lane in ('a','b'):
   assets=scratch/lane/'assets';output=scratch/lane/'build';assets.mkdir(parents=True);inventory=scratch/lane/'inventory.json'
   rootfs=assets/'rootfs-product-xz-128k.squashfs'
   argv=['python3',wsl_path(ROOT/'tools/f341_rootfs_worker.py'),'--source',wsl_path(source_rootfs),'--source-sha256',sha256(source_rootfs),'--source-manifest',wsl_path(a.f340_manifest),'--overlay',wsl_path(overlay),'--module-dir',wsl_path(module_dir),'--closure-manifest',wsl_path(a.closure_manifest),'--engine',wsl_path(Path(closure['engine']['path'])),'--donor-start',wsl_path(ROOT/'versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start'),'--image',wsl_path(rootfs),'--result',wsl_path(inventory),'--build-id',build_id,'--epoch',str(EPOCH)]
   script=scratch/lane/'repack.sh';script.write_bytes(('set -eu\n'+shlex.join(argv)+'\n').encode())
   process=subprocess.run(['wsl.exe','-d',a.distro,'-u','root','-e','sh',wsl_path(script)],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=600)
   if process.returncode:raise RuntimeError(process.stderr[-4000:] or 'F341 rootfs repack failed')
   for suffix,name in KERNEL_FILES.items():shutil.copyfile(source_dir/(source_base+suffix),assets/name)
   settings={'ASSETS':assets,'OUT':output,'BASE':BASE,'ROOTFS_WINDOW':ROOTFS_WINDOW,'SOURCE_DATE_EPOCH':EPOCH};saved={name:getattr(compose,name) for name in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
   try:
    for name,value in settings.items():setattr(compose,name,value)
    compose.f71.TEMPLATE=source_image
    with contextlib.redirect_stdout(log):rc=compose.main()
   finally:
    for name,value in saved.items():setattr(compose,name,value)
    compose.f71.TEMPLATE=template
   require(not rc,'F341 Bootbase composition failed')
   image=output/(BASE+'.webformat.bin');data=image.read_bytes();manifest=json.loads((output/'manifest.json').read_text());inv=json.loads(inventory.read_text())
   require(manifest['contracts']['bootbase']=='PASS' and len(data)<=STORE_OFFSET,'F341 Bootbase/store boundary failed')
   require(data[64:0x180000]==source_image.read_bytes()[64:0x180000],'F341 changed F340 kernel region')
   for suffix in KERNEL_FILES:require(sha256(output/(BASE+suffix))==sha256(source_dir/(source_base+suffix)),'F341 kernel sidecar changed '+suffix)
   require(inv['catalog_verification']['after_unpack']['all_entries_verified'],'post-repack catalog not verified')
   (output/'composition.log').write_text(log.getvalue());shutil.copyfile(inventory,output/'rootfs-inventory.json')
   lane_results.append((output,manifest,inv))
  output,manifest,inv=lane_results[0];other=lane_results[1][0]
  for suffix in ('.webformat.bin','.rootfs.squashfs',*KERNEL_FILES):require(sha256(output/(BASE+suffix))==sha256(other/(BASE+suffix)),'F341 reproduction differs '+suffix)
  manifest.update({'schema':'openmitrastar.f341-native-diagnostic/v1','generated_at_utc':datetime.now(timezone.utc).isoformat(),'classification':'PRIVATE_NATIVE_PIPELINE_DIAGNOSTIC_WATCHDOG_GATED_WIFI_USER_DEFERRED','product_version':PRODUCT_VERSION,'firmware_build_id':build_id,'candidate_eligible':False,'flash_supported':False,'release_eligible':False,
   'source':{'firmware':'F340 watchdog baseline','manifest_sha256':sha256(a.f340_manifest),'candidate_sha256':sha256(source_image),'rootfs_sha256':sha256(source_rootfs),'device_queried':False},
   'frontend':source.get('frontend'),'device_identity':source.get('device_identity'),'web_identity':source.get('web_identity'),'web_security':source.get('web_security'),'storage':source.get('storage'),'recovery':source.get('recovery'),
   'artifact_catalog':inv['catalog_verification'],'module_closure':{'manifest_sha256':sha256(a.closure_manifest),'kernel_config_sha256':closure['kernel_config_sha256'],'modules':{name:{'bytes':row['bytes'],'sha256':row['sha256'],'license':row['license']} for name,row in closure['modules'].items()},'imports_audited':len(closure['imports_audited']),'coherent_full_rebuild':True},
   'diagnostic':{'automatic_acquisition':False,'explicit_controller':'om-f341-diagnostic activate TOKEN32','watchdog_required_before_qdrv':True,'supervisor_protocol':'F340 single-FD authenticated Unix socket ARM/BEGIN/COMPLETE/CEASE','phase_deadline_max_ms':45000,'global_deadline_ms':180000,'channel':36,'bandwidth':80,'radar_callbacks':False,'dfs_tx_authority':False,'software_drain_is_hardware_quiesce':False,'dirty_module_unload':False,'acceptance':'USER_DEFERRED'},
   'inputs':{'tools':tools,'helpers':helpers,'engine_sha256':closure['engine']['sha256']},'change_scope':inv['checks'],'reproducibility':{'independent_rootfs_repack_and_full_composition':2,'all_image_bytes_identical':True,'kernel_reused_exactly_from_F340':True,'all26_modules_rebuilt_twice':True},
   'physical_validation':{'watchdog':'F336_CESSATION_RESET_OBSERVED_ONLY','watchdog_evidence_sha256':sha256(wdt_path),'watchdog_reset_latency_bounds_ms':wdt['evaluation']['reset_latency_bounds_ms'],'watchdog_hardware_reset_cause_verified':False,'watchdog_full_chip_reset_proven':False,'watchdog_CPU_bus_halt_recovery_proven':False,'F340_F341_boot':'UNRUN','radio_acquisition':'USER_DEFERRED','wifi_client':'USER_DEFERRED','RF_CAC_NOP':'USER_DEFERRED','WPS_F335_included':False,'thermal_F339_included':False},
   'safety':{'hardware_actions':False,'flash_go_no_go':'NO_GO_HW_AND_USER_DEFERRED_WIFI','normal_write_target':'mtd4/linux_live only after applicable exact artifact and recovery gates','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],'mtd6':'logical view, not physical partition','watchdog_auto_arm':False}})
  manifest['layout']['mtd_mapping']='F340 kernel/DT unchanged; rootfs at mtd4 slot offset0x180000; store boundary0x5e0000'
  (output/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='ascii')
  shutil.copyfile(a.closure_manifest,output/'module-closure.json')
  for name,path in (('runtime-tests.json',runtime_path),('ipc-tests.json',ipc_path),('control-tests.json',control_path),('supervisor-ipc-tests.json',supervisor_ipc_path),('F336-cessation-evidence.json',wdt_path)):shutil.copyfile(path,output/name)
  for p in source_dir.glob('known_hosts.*'):shutil.copyfile(p,output/'known_hosts.f341')
  (output/'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(output.iterdir()) if p.is_file() and p.name!='SHA256SUMS'),encoding='ascii')
  shutil.copytree(output,final);restrict_acl(final,directory=True)
  for p in final.iterdir():
   if p.is_file():restrict_acl(p,directory=False)
  evidence=ROOT/'outputs/preflight'/('f341-fullimage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));evidence.mkdir(parents=True,exist_ok=False)
  report={'schema':'openmitrastar.f341-fullimage-build/v1','status':'PASS_OFFLINE_FULLIMAGE_NO_GO_HW_WIFI_DEFERRED','candidate':str(final/(BASE+'.webformat.bin')),'manifest':str(final/'manifest.json'),'bytes':manifest['artifacts']['webformat']['bytes'],'sha256':manifest['artifacts']['webformat']['sha256'],'bootbase':'PASS','reproducible':True,'rootfs_headroom':manifest['layout']['rootfs_headroom_bytes'],'hardware':False,'wifi_physical':'USER_DEFERRED'}
  (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(evidence/'result.json'),**report},indent=2))
 finally:
  require(scratch.parent==scratch_root.resolve() and scratch.name.startswith('f341-native-'),'unsafe F341 scratch cleanup')
  shutil.rmtree(scratch)
if __name__=='__main__':main()
