"""Repack exact R8 with qualified R9 observation modules and two shell helpers."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess
from build_f367r8_mode_image import compose,restrict_acl,sha,item,linux,crc,require,EPOCH
from f367r9_rootfs_worker import VERSION,QDRV,WLAN,NATIVE,CONTROL,STATUS,CONTRACT,PROFILE,RELEASE,STORAGE,ARTIFACTS_PATH

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f367r8-f365-mode-contract-device-bound'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.8-f367r9-transition-observation/overlay'
BASE='openmitrastar-linux510-f367r9-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--components',type=Path,required=True);args=parser.parse_args()
 components=json.loads(args.components.read_text())
 require(components['schema']=='openmitrastar.f367r9-transition-components/v1' and components['status']=='PASS_F367R9_TRANSITION_OBSERVATION_COMPONENTS' and components['reproducible'] is True,'R9 components not qualified')
 require(components['qdrv_build_count']==2 and components['wlan_build_count']==1 and bool(components['reproducibility_detail']),'explicit qdrv and preserved peer build provenance')
 input_pins=components['input_pins'];require(input_pins and all(Path(p).is_absolute() and sha(p)==digest for p,digest in input_pins.items()),'component input pins drift')
 refs={key:components[key] for key in ('transition_observation_test','hostlink_trace_test')}
 for ref in refs.values():
  require(sha(ref['path'])==ref['sha256'],'observation proof hash')
  proof=json.loads(Path(ref['path']).read_text());require(proof['status'].startswith('PASS_') and proof['hardware_actions'] is False,'observation proof missing')
  for path,digest in proof['source_pins'].items():require(sha(path)==digest,'observation proof input drift')
 require(refs['hostlink_trace_test']['sha256']=='ce9591acd84c627beff99909dfbdc47fa1b0f92d9626a0c1c9b382518d63857a','reviewed R2 hostlink trace proof')
 require(sha(SOURCE/'manifest.json')=='f01a08379ed4930f1d0c2f00669e74e750a9cdb2f64f51b06865da87c42393d2','R8 manifest drift')
 source=json.loads((SOURCE/'manifest.json').read_text());artifact=components['artifacts']
 for name in ('qdrv','wlan','provider','engine','profile'):
  require(sha(artifact[name]['path'])==artifact[name]['sha256'] and Path(artifact[name]['path']).stat().st_size==artifact[name]['bytes'],'qualified artifact drift '+name)
 for name,path in {'provider':'/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qtn_radar_f367.ko','engine':'/usr/sbin/om-radar-engine-f367','profile':'/usr/sbin/om-f367-dfs-profile'}.items():
  require(artifact[name]['sha256']==source['runtime_bindings'][path],'unchanged native component '+name)
 qdrv=Path(artifact['qdrv']['path']);wlan=Path(artifact['wlan']['path']);control=OVERLAY/CONTROL;status=OVERLAY/STATUS
 for path in (control,status):require(input_pins.get(str(path))==sha(path),'untested overlay '+str(path))
 image=SOURCE/source['artifacts']['webformat']['file'];rootfs=SOURCE/source['artifacts']['rootfs_squashfs']['file'];old=image.name.removesuffix('.webformat.bin')
 require(sha(image)=='7b65b3e66e5d5aafb3db25c0f0622503e4f38a7c1a56f50b97ff2c1969d6d234' and sha(rootfs)==source['artifacts']['rootfs_squashfs']['sha256'],'R8 artifact drift')
 store_spec=source['preserved_store'];store=Path(store_spec['path']).read_bytes();require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'store drift')
 recovery=source['recovery'];fallback=Path(recovery['image']).read_bytes();require(sha(recovery['image'])==recovery['sha256'] and crc(fallback+b'\xff'*(0x5e0000-len(fallback))+store)==recovery['full_slot_crc32_with_preserved_store'],'F365 fallback drift')
 final=DEVICE/'firmware/f367r9-f365-transition-observation-device-bound';require(not final.exists(),'immutable R9 image exists')
 out=DEVICE/'analysis'/('f367r9-fullimage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 input_paths=[Path(__file__).resolve(),ROOT/'tools/f367r9_rootfs_worker.py',ROOT/'tools/build_f367r8_mode_image.py',ROOT/'tools/compose_f164_squashfs_product.py',ROOT/'tools/lyoko_web_rootfs_worker.py',ROOT/'tools/f334_shadow_rootfs_worker.py',ROOT/'tools/f334_shadow_contract.py',args.components.resolve(),SOURCE/'manifest.json',rootfs,image,qdrv,wlan,control,status,Path(store_spec['path']),*(Path(ref['path']) for ref in refs.values())]
 inputs={str(path):sha(path) for path in input_paths};inputs.update(input_pins)
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 campaign=copy.deepcopy(source['campaign']);campaign.update(**refs,runtime_revision='F367r9',shell_runtime_reused_from='F367r8-plus-transition-observation',transition_observation_only=True,trace_first_target_channel=52,trace_window_ms=8000,trace_hostlink_commands=[38,17,35,26],trace_hostlink_line_budget=48,trace_progress_interval_ms=1000,trace_status_requires_env=True,functional_deadlines_unchanged=True)
 fields={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps(dict(build_started=str(out),hardware_actions=False)),flush=True)
 for lane in ('a','b'):
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory=out/lane/'rootfs-inventory.json'
  for suffix,name in fields.items():shutil.copyfile(SOURCE/(old+suffix),assets/name)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f367r9_rootfs_worker.py'),'--source',linux(rootfs),'--source-sha',sha(rootfs),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
  for name,path in (('qdrv',qdrv),('wlan',wlan),('control',control),('status',status)):argv.extend(['--'+name,linux(path),'--'+name+'-sha',sha(path)])
  run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr);require(run.returncode==0,'R9 rootfs worker: '+run.stderr.decode(errors='replace')[-2200:])
  saved={key:getattr(compose,key) for key in ('ASSETS','OUT','BASE','ROOTFS_WINDOW','SOURCE_DATE_EPOCH')};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   compose.ASSETS=assets;compose.OUT=build;compose.BASE=BASE;compose.ROOTFS_WINDOW=0x460000;compose.SOURCE_DATE_EPOCH=EPOCH;compose.f71.TEMPLATE=image
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   for key,value in saved.items():setattr(compose,key,value)
   compose.f71.TEMPLATE=template
  (out/lane/'composition.log').write_text(log.getvalue());require(rc==0,'composition failed')
  composed=json.loads((build/'manifest.json').read_text());delta=json.loads(inventory.read_text());body=(build/(BASE+'.webformat.bin')).read_bytes()
  require(delta['status']=='PASS_F367R9_OBSERVATION_ROOTFS' and delta['all_other_entries_unchanged'] is True,'rootfs delta unqualified')
  require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS' and body[64:0x180000]==image.read_bytes()[64:0x180000],'Bootbase or kernel preservation')
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store;m=copy.deepcopy(source)
  for key in ('layout','kernel','rootfs','artifacts','contracts'):m[key]=composed[key]
  paths=set(source['runtime_bindings'])|{'/'+WLAN};bindings={path:delta['after'][path.lstrip('/')]['sha256'] for path in paths}
  changed={path for path in paths if bindings[path]!=source['runtime_bindings'].get(path)}
  require(changed=={'/'+name for name in (QDRV,WLAN,NATIVE,CONTROL,STATUS,CONTRACT,PROFILE,RELEASE,STORAGE,ARTIFACTS_PATH)},'unexpected runtime delta')
  m.update(schema='openmitrastar.f367r9-transition-observation-image/v1',product_version=VERSION,firmware_build_id=build_id,generated_at_utc=datetime.now(timezone.utc).isoformat(),source={'firmware':'F367r8 exact','image_sha256':sha(image),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},runtime_bindings=bindings,campaign=campaign,native_dfs=delta['native_profile'],recovery=recovery,preserved_store=store_spec,change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'observation_only':True,'kernel_provider_engine_static_helper_supervisor_unchanged':True,'native_helper_only_hash_pins_changed':True},revision={'scope':'bounded first52 CSA/caller/hostlink/calstate/clock and getter/snapshot observation; no policy or deadline changes','previous_manifest_sha256':sha(SOURCE/'manifest.json')},reproducibility={'qdrv_build_count':components['qdrv_build_count'],'wlan_build_count':components['wlan_build_count'],'component_detail':components['reproducibility_detail'],'other_modules_and_binaries_reused':True,'rootfs_repacked_twice':True,'epoch':EPOCH},physical_validation={'observation_gate':'UNRUN','RF_CAC_NOP':'UNRUN','wifi_client_traffic':'UNRUN'})
  m['module_closure']['native_components']=item(args.components);m['module_closure']['imports_audited']=len(components['imports_audited'])
  m['layout']['firmware_prefix_crc32']=crc(prefix);m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, not FF padding'}
  (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inventory,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f367',build/'known_hosts.f367')
  (build/'LAYOUT.md').write_text('# F367r9 transition observation\n\nOnly qdrv/wlan observation, controller/status trace, loader pins and metadata differ from R8. Kernel, DT, other runtime bytes, exact F365 recovery and store are preserved. Functional behavior and deadlines remain unchanged; logging adds bounded observation overhead. RF/CAC/NOP/client acceptance remains pending.\n')
  (build/'SHA256SUMS').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in sorted(build.iterdir()) if path.is_file() and path.name!='SHA256SUMS'))
 for suffix in (*fields,'.rootfs.squashfs','.webformat.bin'):require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
 for path,digest in inputs.items():require(sha(path)==digest,'input changed during composition')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for path in final.iterdir():
  if path.is_file():restrict_acl(path,directory=False)
 m=json.loads((final/'manifest.json').read_text())
 result=dict(schema=m['schema'],status='PASS_OFFLINE_F367R9_TRANSITION_OBSERVATION_IMAGE',artifact=item(final/(BASE+'.webformat.bin')),manifest=str(final/'manifest.json'),manifest_sha256=sha(final/'manifest.json'),product_version=VERSION,firmware_build_id=build_id,reproducible=True,bootbase='PASS',slot_fit=True,rootfs_headroom=m['layout']['rootfs_headroom_bytes'],prefix_crc32=m['layout']['firmware_prefix_crc32'],full_slot=m['artifacts']['full_slot'],preserved_store=store_spec,recovery=recovery,runtime_bindings=m['runtime_bindings'],campaign=campaign,rootfs_changed_files=m['change_scope']['files'],hardware_actions=False,flash_go_no_go='OFFLINE_GO_OBSERVATION_GATE_WITH_MANDATORY_F365_RETURN')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2))
if __name__=='__main__':main()
