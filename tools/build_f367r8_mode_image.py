"""Compose R6 from sealed R5 after the exact static helper target probe."""
from pathlib import Path
from datetime import datetime,timezone
import contextlib,copy,hashlib,io,json,shutil,subprocess,zlib
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f367r8_rootfs_worker import VERSION
from f367r6_rootfs_worker import static_elf
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f367r7-f365-clock-observation-device-bound'
MODE_TEST=ROOT/'outputs/preflight/f367r8-mode-contract-20260922T211028Z/result.json'
CONTROL=ROOT/'versions/lyoko-foundation-6.11.7-f367r8-mode-contract/overlay/usr/sbin/om-f367-control'
STATIC=ROOT/'outputs/kernel-port/f367r6-static-qualified-20260922T183736Z/result.json'
PROBE=ROOT/'outputs/handoff-live/f367r6-static-probe-20260922T183941Z/result.json'
BASE='openmitrastar-linux510-f367r8-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
EPOCH=1790006400
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def crc(data):return f'{zlib.crc32(data)&0xffffffff:08x}'
def require(value,reason):
 if not value:raise ValueError(reason)
def main():
 test=json.loads(MODE_TEST.read_text())
 require(test['status']=='PASS_OEM_MODE_PARSER_AND_BOUNDED_CSA_OBSERVER' and len(test['helper_cases'])==5 and all(x['passed'] for x in test['helper_cases']),'mode/observer qualification missing')
 for path,digest in test['source_pins'].items():require(sha(path)==digest,'mode proof source drift')
 require(test['source_pins'][str(CONTROL)]==sha(CONTROL),'controller differs from tested bytes')
 require(sha(SOURCE/'manifest.json')=='3ce8489e85b0d0d9292932bd7b48086a880575e276fc6915dcbc1bc70ca433f4','sealed R5 manifest drift')
 require(sha(PROBE)=='a700450d7f2ada90973472c40f8980a5312299d95ba3e29b25eede5a6f387636','exact target execution proof required')
 source=json.loads((SOURCE/'manifest.json').read_text());static=json.loads(STATIC.read_text());probe=json.loads(PROBE.read_text())
 require(static['status']=='PASS_OFFLINE_F367R6_STATIC_PROFILE' and static['reproducible'] and static['source_logic_unchanged'],'static helper unqualified')
 helper=Path(static['artifact']['path']);require(sha(helper)==static['artifact']['sha256']==probe['artifact_sha256'],'target helper bytes differ')
 require(probe['status']=='PASS' and probe['exit_code']==0 and probe['stderr']=='' and probe['fixture_removed'] and probe['cleanup_exit']==0 and probe['stdout']=='F367R6_STATIC_EXEC_PASS invalid_argument_exit=1\n','target probe did not pass')
 require(probe['probe_argument']=='__F367R6_INVALID_ARGUMENT_PROBE__' and probe['probe_sha256']==static['probe']['sha256'] and sha(static['probe']['path'])==probe['probe_sha256'],'probe mismatch')
 require(static['static_link'] and not static['pt_interp'] and not static['pt_dynamic'] and static['dt_needed']==[] and static['atomic_policy']['llock_instructions']==static['atomic_policy']['scond_instructions']==0,'loader or atomic dependency remains')
 static_elf(helper.read_bytes())
 for path,digest in static['source_pins'].items():require(sha(path)==digest,'static source drift')
 components_path=Path(static['reused_r5_components']['path']);require(sha(components_path)==static['reused_r5_components']['sha256'],'R5 qualification drift')
 components=json.loads(components_path.read_text())
 for path,digest in components['userspace_pins'].items():require(sha(path)==digest and any(Path(p).name==Path(path).name and h==digest for p,h in static['source_pins'].items()),'publisher logic changed')
 route=source['campaign']['regulatory_profile_test'];require(route['sha256']==static['reused_regulatory_tests']['sha256'] and sha(route['path'])==route['sha256'],'R5 tests not reused exactly')
 image=SOURCE/source['artifacts']['webformat']['file'];rootfs=SOURCE/source['artifacts']['rootfs_squashfs']['file'];old=image.name.removesuffix('.webformat.bin')
 require(sha(image)=='5cd4118bc84061da24f917b99978477c85a405dba613743d6398ba2894a7e28c' and sha(rootfs)==source['artifacts']['rootfs_squashfs']['sha256'],'sealed R5 artifact drift')
 store_spec=source['preserved_store'];store=Path(store_spec['path']).read_bytes();require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'store drift')
 recovery=source['recovery'];fallback=Path(recovery['image']).read_bytes();require(sha(recovery['image'])==recovery['sha256'] and crc(fallback+b'\xff'*(0x5e0000-len(fallback))+store)==recovery['full_slot_crc32_with_preserved_store'],'F365 fallback drift')
 final=DEVICE/'firmware/f367r8-f365-mode-contract-device-bound';require(not final.exists(),'immutable R6 image exists')
 out=DEVICE/'analysis'/('f367r8-fullimage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f367r6_rootfs_worker.py',ROOT/'tools/f367r8_rootfs_worker.py',MODE_TEST,CONTROL,STATIC,PROBE,SOURCE/'manifest.json',helper,components_path,Path(route['path']),Path(static['probe']['path']),Path(store_spec['path'])]}
 inputs.update(static['source_pins'])
 inputs.update(test['source_pins'])
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 campaign=copy.deepcopy(source['campaign']);campaign.update(mode_contract_test=item(MODE_TEST),mode_setter_request='11ac',mode_getter_label='11ac20',channel_context_readback_deadline_ms=5000,one_write_per_mode_filter_channel=True,context_fault_before_success=True,runtime_revision='F367r8',shell_runtime_reused_from='F367r7-except-controller',regulatory_profile_helper={'path':'/usr/sbin/om-f367-dfs-profile','sha256':sha(helper)},static_profile_qualification=item(STATIC),static_profile_target_probe=item(PROBE),profile_helper_static=True)
 fields={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps(dict(build_started=str(out),hardware_actions=False)),flush=True)
 for lane in ('a','b'):
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory=out/lane/'rootfs-inventory.json'
  for suffix,name in fields.items():shutil.copyfile(SOURCE/(old+suffix),assets/name)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f367r8_rootfs_worker.py'),'--source',linux(rootfs),'--source-sha',sha(rootfs),'--control',linux(CONTROL),'--control-sha',sha(CONTROL),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
  run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr);require(run.returncode==0,'static rootfs worker: '+run.stderr.decode(errors='replace')[-2200:])
  saved={k:getattr(compose,k) for k in ('ASSETS','OUT','BASE','ROOTFS_WINDOW','SOURCE_DATE_EPOCH')};template=compose.f71.TEMPLATE;log=io.StringIO()
  try:
   compose.ASSETS=assets;compose.OUT=build;compose.BASE=BASE;compose.ROOTFS_WINDOW=0x460000;compose.SOURCE_DATE_EPOCH=EPOCH;compose.f71.TEMPLATE=image
   with contextlib.redirect_stdout(log):rc=compose.main()
  finally:
   for k,v in saved.items():setattr(compose,k,v)
   compose.f71.TEMPLATE=template
  (out/lane/'composition.log').write_text(log.getvalue());require(rc==0,'composition failed')
  composed=json.loads((build/'manifest.json').read_text());delta=json.loads(inventory.read_text());body=(build/(BASE+'.webformat.bin')).read_bytes()
  require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS' and body[64:0x180000]==image.read_bytes()[64:0x180000],'Bootbase or kernel preservation failed')
  prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store;m=copy.deepcopy(source)
  for key in ('layout','kernel','rootfs','artifacts','contracts'):m[key]=composed[key]
  bindings={path:delta['after'][path.lstrip('/')]['sha256'] for path in source['runtime_bindings']}
  allowed={'/usr/sbin/om-f367-control','/etc/openmitrastar/release','/usr/share/openmitrastar/dfs-f367/profile.json','/usr/share/openmitrastar/radio5g/artifacts.sha256','/usr/share/openmitrastar/storage/artifacts.sha256'}
  require({p for p in bindings if bindings[p]!=source['runtime_bindings'][p]}==allowed,'unexpected runtime delta')
  m.update(schema='openmitrastar.f367r8-mode-contract-image/v1',product_version=VERSION,firmware_build_id=build_id,generated_at_utc=datetime.now(timezone.utc).isoformat(),source={'firmware':'F367r7 exact','image_sha256':sha(image),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},runtime_bindings=bindings,campaign=campaign,native_dfs=delta['native_profile'],recovery=recovery,preserved_store=store_spec,change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'only_controller_and_metadata':True,'qdrv_kernel_provider_engine_supervisor_native_helpers_unchanged':True},revision={'scope':'OEM setter token11ac, safe request/rc markers, bounded CSA context readback; fault checked before success','previous_manifest_sha256':sha(SOURCE/'manifest.json')},reproducibility={'all_modules_and_native_binaries_reused':True,'no_compilation':True,'rootfs_repacked_twice':True,'epoch':EPOCH},physical_validation={'static_helper_execution':'PASS_INVALID_ARGUMENT_ONLY','regulatory_publication':'UNRUN','RF_CAC_NOP':'UNRUN','wifi_client_traffic':'UNRUN'})
  m['layout']['firmware_prefix_crc32']=crc(prefix);m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, not FF padding'}
  (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inventory,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f367',build/'known_hosts.f367')
  (build/'LAYOUT.md').write_text('# F367r8 mode setter and CSA observer\n\nOnly om-f367-control and release/profile/catalog metadata differ from R7. All modules and native binaries are byte-identical. Setter11ac maps to getter11ac20; the observer waits up to5s without repeating any write or moving deadlines. Exact F365 recovery and store are preserved. No loader is needed. Target invalid-argument execution passed; regulatory publication/CAC/NOP/client traffic remain physical gates.\n')
  (build/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in (*fields,'.rootfs.squashfs','.webformat.bin'):require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
 for path,digest in inputs.items():require(sha(path)==digest,'input changed during composition')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text())
 result=dict(schema=m['schema'],status='PASS_OFFLINE_F367R8_MODE_CONTRACT_IMAGE',artifact=item(final/(BASE+'.webformat.bin')),manifest=str(final/'manifest.json'),manifest_sha256=sha(final/'manifest.json'),product_version=VERSION,firmware_build_id=build_id,reproducible=True,bootbase='PASS',slot_fit=True,rootfs_headroom=m['layout']['rootfs_headroom_bytes'],prefix_crc32=m['layout']['firmware_prefix_crc32'],full_slot=m['artifacts']['full_slot'],preserved_store=store_spec,recovery=recovery,runtime_bindings=m['runtime_bindings'],campaign=campaign,rootfs_changed_files=m['change_scope']['files'],hardware_actions=False,flash_go_no_go='OFFLINE_GO_REGULATORY_CAC_NOP_CLIENT_GATE_AND_F365_RETURN_PENDING')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**result),indent=2))
if __name__=='__main__':main()
