"""Compose a reproducible F366 native diagnostic full image from exact F365."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess,zlib
import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f367_runtime_contract import VERSION,overlay
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f365-f364r3-temperature-data-device-bound'
BASE='openmitrastar-linux510-f367-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
EPOCH=1790006400
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def crc(data):return f'{zlib.crc32(data)&0xffffffff:08x}'
def require(v,m):
 if not v:raise ValueError(m)
def item(p):p=Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--components-result',type=Path,required=True);ap.add_argument('--runtime-result',type=Path,required=True);ap.add_argument('--functional-tests-result',type=Path,required=True);ap.add_argument('--supervisor-result',type=Path,required=True);a=ap.parse_args()
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 require(sha(SOURCE/'manifest.json')=='a73a41e32d793a33ec13c46ef62bbf5890039339d38ef107d04c13b91e19d19c','F365 manifest drift')
 source=json.loads((SOURCE/'manifest.json').read_text());c=json.loads(a.components_result.read_text());runtime=json.loads(a.runtime_result.read_text())
 require(c['status']=='PASS_F367_BUILD_LINK_AND_REPRODUCTION' and c['reproducible'],'native components not qualified')
 require(runtime['status']=='PASS_F367_ACTUAL_HELPERS_AND_V2_IPC','F366 runtime not qualified')
 functional_path=a.functional_tests_result;functional=json.loads(functional_path.read_text())
 normalize=lambda rows:{name.replace('\\','/'):digest for name,digest in rows.items()}
 require(functional['status']=='PASS_ACTUAL_CONTEXT_POLICY_CONTROLS_AND_SNAPSHOT' and normalize(functional['source_pins'])==normalize(c['source_pins']),'affected functional source checks required')
 supervisor=json.loads(a.supervisor_result.read_text())
 require(supervisor['status']=='PASS_OFFLINE_F367_SUPERVISOR' and supervisor['reproducible'] and supervisor['wire_version']==2 and supervisor['health_lease_ms']==5000 and supervisor['total_budget_max_ms']==5400000 and supervisor['phase_budget_max_ms']==60000 and supervisor['phase_sequence_max']==128,'supervisor contract mismatch')
 require(sha(supervisor['artifact']['path'])==supervisor['artifact']['sha256']=='ecd861a42812a8516f81e38fdad081089639f77a61c56335bf6c1110a926a477','supervisor artifact drift')
 for path,digest in supervisor['sources'].items():require(sha(path)==digest,'supervisor qualified source drift')
 physical=ROOT/'outputs/acceptance/f366r3-acquisition-addendum-20260922T114659Z/result.json'
 require(sha(physical)=='9201514a074decb9987cdaa174f25c19739ddc083e9a842179fec77cc633fb87','R3 acquisition acceptance required')
 accepted=json.loads(physical.read_text())
 require(accepted['status']=='PASS_F366R3_NATIVE_ACQUISITION_WITH_F365_RETURN_ADDENDUM','R3 prerequisite status')
 for path,digest in accepted['evidence'].items():require(sha(path)==digest,'R3 evidence drift')
 r3_manifest=next(Path(path) for path in accepted['evidence'] if path.endswith('manifest.json') and 'f366r3-' in path)
 r3_inputs=json.loads(r3_manifest.read_text())['source']['inputs']
 for name in ('f366_runtime_contract.py','f366r2_runtime_contract.py','f366r3_runtime_contract.py'):
  matches=[digest for path,digest in r3_inputs.items() if path.endswith(name)]
  require(len(matches)==1 and sha(ROOT/'tools'/name)==matches[0],'accepted bootstrap source drift '+name)
 campaign={'callback_authority':1,'bootstrap_channel':36,'bootstrap_bandwidth':80,'dfs_channel':52,'dfs_bandwidth':20,'escape_channel':36,'quarantine_ms':1800000,'cac_ms':70000,'nop_ms':1800000,'supervisor_total_ms':5400000,'supervisor':{'path':'/usr/sbin/om-watchdog-supervisor-f367','sha256':supervisor['artifact']['sha256']},'acquisition_acceptance':{'path':str(physical),'sha256':sha(physical)},'commands':{'activate':'om-f367-control activate TOKEN32','status':'om-f367-control status','enter_dfs':'om-f367-control enter-dfs','software_radar':'om-f367-control software-radar','stop':'om-f367-control stop'},'software_injection_is_rf_detection':False}
 for p,h in runtime['source_pins'].items():require(sha(p)==h,'runtime qualification drift')
 for name,data in overlay().items():require(hashlib.sha256(data).hexdigest()==runtime['helpers'][name],'helper changed after tests '+name)
 for row in c['artifacts'].values():require(sha(row['path'])==row['sha256'],'component drift')
 for name,h in c['source_pins'].items():require(sha(ROOT/'work/kernel-port/f367-functional'/name)==h,'component source drift')
 image=SOURCE/source['artifacts']['webformat']['file'];old=image.name.removesuffix('.webformat.bin');rootfs=SOURCE/source['artifacts']['rootfs_squashfs']['file']
 require(sha(image)=='43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355','F365 image drift')
 require(c['kernel_config_sha256']==source['artifacts']['config']['sha256'] and c['kernel_vmlinux_sha256']==sha(SOURCE/(old+'.vmlinux')),'native ABI mismatch')
 store_spec=source['preserved_store'];store=Path(store_spec['path']).read_bytes()
 require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'journal evidence drift')
 fallback=image.read_bytes();fprefix=fallback+b'\xff'*(0x5e0000-len(fallback));ffull=fprefix+store
 require(crc(ffull)==source['artifacts']['full_slot']['crc32'],'F365 fallback full slot mismatch')
 final=DEVICE/'firmware/f367-f365-ap-dfs-device-bound';require(not final.exists(),'immutable F366 image already exists')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f367-fullimage-'+stamp);out.mkdir(parents=True,exist_ok=False)
 inputs={str(p):sha(p) for p in [Path(__file__),ROOT/'tools/f367_rootfs_worker.py',ROOT/'tools/f367_runtime_contract.py',a.components_result,a.runtime_result,functional_path,a.supervisor_result,physical,SOURCE/'manifest.json',ROOT/'tools/f366_runtime_contract.py',ROOT/'tools/f366r2_runtime_contract.py',ROOT/'tools/f366r3_runtime_contract.py',ROOT/'work/kernel-port/f367-functional/source-manifest.json',Path(store_spec['path'])]}
 build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
 fields={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
 print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 for lane in ('a','b'):
  assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inv=out/lane/'rootfs-inventory.json'
  for suffix,name in fields.items():shutil.copyfile(SOURCE/(old+suffix),assets/name)
  argv=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(ROOT/'tools/f367_rootfs_worker.py'),'--source',linux(rootfs),'--source-sha',sha(rootfs),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inv)]
  for name in ('qdrv','provider','engine'):argv+=['--'+name,linux(c['artifacts'][name]['path']),'--'+name+'-sha',c['artifacts'][name]['sha256']]
  argv+=['--supervisor',linux(supervisor['artifact']['path']),'--supervisor-sha',supervisor['artifact']['sha256']]
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
  m.update(schema='openmitrastar.f367-ap-dfs-image/v1',classification='CONTROLLED_AP52_BW20_CAC_NOP_CANDIDATE',product_version=VERSION,firmware_build_id=build_id,generated_at_utc=stamp,candidate_eligible=True,flash_supported=False,release_eligible=False,source={'firmware':'F365 exact','image_sha256':sha(image),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'kernel_config_dt_ethernet_sensor_watchdog_unchanged':True,'qdrv_f355_lifetime_preserved':True,'native_radar_only':True},preserved_store=store_spec,recovery=recovery,reproducibility={'kernel_not_recompiled':True,'qdrv_provider_built_twice':True,'engine_exact_qualified_f338':True,'rootfs_repacked_twice':True,'epoch':EPOCH},physical_validation={'status':'UNRUN','acquisition':'UNRUN','RF_CAC_NOP':'UNRUN','wifi_client_traffic':'UNRUN','temperature':'UNACCEPTED_PRIOR_ETIMEDOUT'},native_dfs=delta['native_profile'],runtime_bindings=delta['runtime_bindings'],module_closure={'native_components':item(a.components_result),'module_count':len(c['modules']),'imports_audited':len(c['imports_audited']),'load_order':c['load_order'],'kernel_config_sha256':c['kernel_config_sha256'],'qdrv_internal_compat_linked':False,'f355_lifetime_preserved':True,'taint_conflicts':False},campaign=campaign,functional_tests=item(functional_path),supervisor_qualification=item(a.supervisor_result),safety={'hardware_actions':False,'normal_write_target':'physical mtd4/linux_live at0x7e0000','write_prefix_bytes':0x5e0000,'firmware_erase_end_exclusive':'0xdc0000','protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],'automatic_arm':False,'automatic_reboot':False,'sensor_mmio_at_boot':False,'flash_go_no_go':'OFFLINE_GO_CAC_NOP_CLIENT_PHYSICAL_GATE_AND_F365_RETURN_PENDING'})
  m['layout']['firmware_prefix_crc32']=crc(prefix);m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, not FF padding'}
  (build/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');shutil.copyfile(inv,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f365',build/'known_hosts.f367')
  shutil.copyfile(a.components_result,build/'native-components.json');shutil.copyfile(a.runtime_result,build/'runtime-tests.json')
  (build/'LAYOUT.md').write_text('# F367 controlled AP DFS52/20 candidate\n\nExact F365 kernel/DT/Ethernet/temperature/journal and F355 lifetime. Proof-bound native callback authority after accepted R3 acquisition. Bootstrap36/80, local1800s quarantine, AP52/20 with full70s CAC, continuous detector continuity, fallback36 and1800s NOP. Separate supervisor90min/HEALTH5s. Bootpending, no auto-arm. Software injection is not RF detection. Root must validate CAC/client/NOP and return exact F365.\n')
  (build/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(build.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
 for suffix in (*fields,'.rootfs.squashfs','.webformat.bin'):require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
 for p,h in inputs.items():require(sha(p)==h,'composition input changed')
 shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
 for p in final.iterdir():
  if p.is_file():restrict_acl(p,directory=False)
 m=json.loads((final/'manifest.json').read_text());candidate=final/(BASE+'.webformat.bin')
 result={'schema':'openmitrastar.f367-ap-dfs-image/v1','status':'PASS_OFFLINE_F367_AP_DFS_IMAGE','artifact':item(candidate),'manifest':str(final/'manifest.json'),'manifest_sha256':sha(final/'manifest.json'),'product_version':VERSION,'firmware_build_id':build_id,'reproducible':True,'bootbase':'PASS','slot_fit':True,'rootfs_headroom':m['layout']['rootfs_headroom_bytes'],'prefix_crc32':m['layout']['firmware_prefix_crc32'],'full_slot':m['artifacts']['full_slot'],'preserved_store':store_spec,'recovery':m['recovery'],'runtime_bindings':m['runtime_bindings'],'campaign':m['campaign'],'rootfs_changed_files':m['change_scope']['files'],'hardware_actions':False,'flash_go_no_go':m['safety']['flash_go_no_go']}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2))
if __name__=='__main__':main()
