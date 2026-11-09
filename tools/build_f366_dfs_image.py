"""Compose a reproducible F366 native diagnostic full image from exact F365."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess,zlib
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f366_runtime_contract import VERSION,overlay
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f365-f364r3-temperature-data-device-bound'
BASE='openmitrastar-linux510-f366-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
EPOCH=1790006400
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def crc(data):return f'{zlib.crc32(data)&0xffffffff:08x}'
def require(v,m):
 if not v:raise ValueError(m)
def item(p):p=Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--components-result',type=Path,required=True);ap.add_argument('--runtime-result',type=Path,required=True);a=ap.parse_args()
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 require(sha(SOURCE/'manifest.json')=='a73a41e32d793a33ec13c46ef62bbf5890039339d38ef107d04c13b91e19d19c','F365 manifest drift')
 source=json.loads((SOURCE/'manifest.json').read_text());c=json.loads(a.components_result.read_text());runtime=json.loads(a.runtime_result.read_text())
 require(c['status']=='PASS_OFFLINE_NATIVE_DFS_DIAGNOSTIC_COMPONENTS' and c['reproducible'],'native components not qualified')
 require(runtime['status']=='PASS_F366_RUNTIME_AND_ACTUAL_WATCHDOG_IPC','F366 runtime not qualified')
 for p,h in runtime['source_pins'].items():require(sha(p)==h,'runtime qualification drift')
 for name,data in overlay().items():require(hashlib.sha256(data).hexdigest()==runtime['helpers'][name],'helper changed after tests '+name)
 for row in c['artifacts'].values():require(sha(row['path'])==row['sha256'],'component drift')
 for name,h in c['source_pins'].items():require(sha(ROOT/'work/kernel-port/f366'/name)==h,'component source drift')
 image=SOURCE/source['artifacts']['webformat']['file'];old=image.name.removesuffix('.webformat.bin');rootfs=SOURCE/source['artifacts']['rootfs_squashfs']['file']
 require(sha(image)=='43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355','F365 image drift')
 require(c['kernel_config_sha256']==source['artifacts']['config']['sha256'] and c['kernel_vmlinux_sha256']==sha(SOURCE/(old+'.vmlinux')),'native ABI mismatch')
 store_spec=source['preserved_store'];store=Path(store_spec['path']).read_bytes()
 require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'journal evidence drift')
 fallback=image.read_bytes();fprefix=fallback+b'\xff'*(0x5e0000-len(fallback));ffull=fprefix+store
 require(crc(ffull)==source['artifacts']['full_slot']['crc32'],'F365 fallback full slot mismatch')
 final=DEVICE/'firmware/f366-f365-native-dfs-diagnostic-device-bound';require(not final.exists(),'immutable F366 image already exists')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f366-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f366_rootfs_worker.py',ROOT/'tools/f366_runtime_contract.py',a.components_result,a.runtime_result,SOURCE/'manifest.json',ROOT/'work/kernel-port/f366/source-manifest.json',Path(store_spec['path'])]}
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 fields={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 for lane in ('a','b'):
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inv=out/lane/'rootfs-inventory.json'
  for suffix,name in fields.items():shutil.copyfile(SOURCE/(old+suffix),assets/name)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f366_rootfs_worker.py'),'--source',linux(rootfs),'--source-sha',sha(rootfs),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inv)]
  for name in ('qdrv','provider','engine'):argv+=['--'+name,linux(c['artifacts'][name]['path']),'--'+name+'-sha',c['artifacts'][name]['sha256']]
  run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr)
  require(run.returncode==0,'rootfs worker failed '+run.stderr.decode(errors='replace')[-1800:])
  settings={'ASSETS':assets,'OUT':build,'BASE':BASE,'ROOTFS_WINDOW':0x460000,'SOURCE_DATE_EPOCH':EPOCH};saved={k:getattr(compose,k) for k in settings};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   for k,v in settings.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=image
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   compose.f71.TEMPLATE=template
   for k,v in saved.items():setattr(compose,k,v)
  (out/lane/'composition.log').write_text(log.getvalue());require(rc==0,'composition failed')
  composed=json.loads((build/'manifest.json').read_text());delta=json.loads(inv.read_text());candidate=build/(BASE+'.webformat.bin');body=candidate.read_bytes()
  require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS','Bootbase/store overlap')
  require(body[64:0x180000]==fallback[64:0x180000],'F365 kernel flash bytes changed')
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store;m=copy.deepcopy(source)
  for key in ('layout','kernel','rootfs','artifacts','contracts'):m[key]=composed[key]
  recovery={'image':str(image),'sha256':sha(image),'bytes':len(fallback),'version':source['product_version'],'kernel_build':'#358','prefix_crc32':crc(fprefix),'full_slot_crc32_with_preserved_store':crc(ffull),'store_must_be_preserved':True,'physical_baseline_and_recovery_acceptance':'root binds exact accepted F365 evidence'}
  m.update(schema='openmitrastar.f366-native-dfs-image/v1',classification='F365_WITH_NATIVE_DFS_ACQUISITION_DIAGNOSTIC_AUTHORITY_DISABLED',product_version=VERSION,firmware_build_id=build_id,generated_at_utc=stamp,candidate_eligible=True,flash_supported=False,release_eligible=False,source={'firmware':'F365 exact','image_sha256':sha(image),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'kernel_config_dt_ethernet_sensor_watchdog_unchanged':True,'qdrv_f355_lifetime_preserved':True,'native_radar_only':True},preserved_store=store_spec,recovery=recovery,reproducibility={'kernel_not_recompiled':True,'qdrv_provider_built_twice':True,'engine_exact_qualified_f338':True,'rootfs_repacked_twice':True,'epoch':EPOCH},physical_validation={'status':'UNRUN','acquisition':'UNRUN','RF_CAC_NOP':'UNRUN','wifi_client_traffic':'UNRUN','temperature':'UNACCEPTED_PRIOR_ETIMEDOUT'},native_dfs=delta['native_profile'],runtime_bindings=delta['runtime_bindings'],module_closure={'native_components':item(a.components_result),'module_count':len(c['modules']),'imports_audited':len(c['imports_audited']),'load_order':c['load_order'],'kernel_config_sha256':c['kernel_config_sha256'],'qdrv_internal_compat_linked':False,'f355_lifetime_preserved':True,'taint_conflicts':False},diagnostic={'controller':'om-f366-diagnostic activate TOKEN32','status':'om-f366-status','stop':'STOP_DIAGNOSTIC','callback_authority':0,'diagnostic_channel':36,'bandwidth':80,'watchdog_session_ms':180000,'five_ghz_boot_pending':True,'continuous_native_acquisition':True,'release_qualified':False,'runtime_tests':item(a.runtime_result)},safety={'hardware_actions':False,'normal_write_target':'physical mtd4/linux_live at0x7e0000','write_prefix_bytes':0x5e0000,'firmware_erase_end_exclusive':'0xdc0000','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],'automatic_arm':False,'automatic_reboot':False,'sensor_mmio_at_boot':False,'flash_go_no_go':'OFFLINE_GO_EXACT_PHYSICAL_GATE_AND_F365_RETURN_PENDING'})
  m['layout']['firmware_prefix_crc32']=crc(prefix);m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, not FF padding'}
  (build/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');shutil.copyfile(inv,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f365',build/'known_hosts.f366')
  shutil.copyfile(a.components_result,build/'native-components.json');shutil.copyfile(a.runtime_result,build/'runtime-tests.json')
  (build/'LAYOUT.md').write_text('# F366 native DFS acquisition diagnostic\n\nExact F365 kernel/DT/Ethernet/watchdog/sensor/journal. Native F333 acquisition, F331 GPL postfilter, F338 userspace engine and readiness, F341 diagnostic telemetry. F355 lifetime remains. 5 GHz is pending at boot; explicit once-per-boot acquisition is restricted to channel36/BW80 and watchdog180s. DFS authority is compiled off. This is not RF/CAC/NOP or release acceptance. The root physical campaign must restore the exact F365 image and preserve journal.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in (*fields,'.rootfs.squashfs','.webformat.bin'):require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
 for p,h in inputs.items():require(sha(p)==h,'composition input changed')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text());candidate=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f366-native-dfs-image/v1','status':'PASS_OFFLINE_NATIVE_DFS_DIAGNOSTIC_IMAGE','artifact':item(candidate),'manifest':str(final/'manifest.json'),'manifest_sha256':sha(final/'manifest.json'),'product_version':VERSION,'firmware_build_id':build_id,'reproducible':True,'bootbase':'PASS','slot_fit':True,'rootfs_headroom':m['layout']['rootfs_headroom_bytes'],'prefix_crc32':m['layout']['firmware_prefix_crc32'],'full_slot':m['artifacts']['full_slot'],'preserved_store':store_spec,'recovery':m['recovery'],'runtime_bindings':m['runtime_bindings'],'diagnostic':m['diagnostic'],'rootfs_changed_files':m['change_scope']['files'],'hardware_actions':False,'flash_go_no_go':m['safety']['flash_go_no_go']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2))
if __name__=='__main__':main()
