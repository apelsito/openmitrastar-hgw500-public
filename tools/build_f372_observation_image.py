"""Compose an exact-qualified F370 QDRV into F372 atop F371; offline only."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess
from build_f367r8_mode_image import compose,restrict_acl,sha,item,linux,crc,require,EPOCH
from build_f369_store38_image import native_path
from f372_rootfs_worker import VERSION,ALLOWED,QDRV,WLAN

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f371-f365-normal-start-compat-device-bound'
BASE='openmitrastar-linux510-f372-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
FIELDS={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}
PARAMETERS={'openmitrastar_auc_raw_ok','openmitrastar_auc_raw_other','openmitrastar_auc_busy_free','openmitrastar_auc_return_success'}

def verify_artifact(row):
    path=native_path(row['path']); require(sha(path)==row['sha256'] and path.stat().st_size==row['bytes'],'artifact drift '+str(path)); return path

def source_path(name):
    if name.startswith('/home/'):
        return Path('//wsl.localhost/REA-Linux'+name)
    return native_path(name)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--qualification-sha',required=True)
    p.add_argument('--qdrv',type=Path,required=True)
    p.add_argument('--qdrv-sha',required=True)
    p.add_argument('--distro',default='REA-Linux'); a=p.parse_args()
    require(sha(a.qualification)==a.qualification_sha,'qualification receipt drift')
    proof=json.loads(a.qualification.read_text())
    require(proof['schema']=='openmitrastar.f370-module-qualification/v1' and proof['status']=='PASS_OFFLINE_COMPLETE_MODULE' and proof['full_baseline_comparison_status']=='PASS_FULL_BASELINE_RECONSTRUCTION','full qualification, not pending baseline comparison, required')
    require(proof['reproducible'] is True and proof['hardware_accessed'] is False and proof['inputs_unchanged'] is True,'qualification scope differs')
    require(proof['imports_unchanged']==369 and proof['exports_unchanged']==15,'F365 module ABI closure differs')
    require(set(proof['new_parameters_0444'])==PARAMETERS,'observation parameters differ')
    module_build_dir=a.qualification.parent.parent
    build_proof_path=module_build_dir/'result.json'; build_proof=json.loads(build_proof_path.read_text())
    require(build_proof['status']=='PASS_BUILD_PENDING_FULL_BASELINE_COMPARISON' and build_proof['reproducible'] is True and build_proof['source_inputs_unchanged'] is True,'qualified original build differs')
    comparison_path=a.qualification.parent/'full-baseline-comparison.json'; comparison=json.loads(comparison_path.read_text())
    allowed_separate={'BUILD_METADATA_SEPARATELY_VALIDATED','ALL_RELA_RECORDS_CANONICALIZED_SEPARATELY'}
    require(comparison['status']=='PASS_FULL_BASELINE_RECONSTRUCTION' and comparison['errors']==[] and all(section.get('pass') is True or section.get('comparison') in allowed_separate for section in comparison['sections']),'baseline reconstruction does not pass')
    require(comparison['relocations_all_match'] is True and comparison['relocation_differences']==[] and comparison['symbol_differences']==[] and comparison['function_count']==831 and comparison['relocations_total']==14034 and comparison['symbols_total']==1932,'baseline semantics missing')
    modules={row['lane']:row for row in build_proof['modules']}
    require({'baseline','a','b'}<=modules.keys(),'baseline and two candidates absent')
    require(modules['a']['sha256']==modules['b']['sha256']==a.qdrv_sha,'two-build candidate mismatch')
    verify_artifact(modules['a']); verify_artifact(modules['b'])
    require(sha(a.qdrv)==a.qdrv_sha and a.qdrv.stat().st_size==modules['a']['bytes'],'root supplied artifact receipt mismatch')
    require(build_proof['parent_module_sha256']=='cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01','wrong F365 lineage')
    require(proof['module']['sha256']==a.qdrv_sha and proof['module']['bytes']==a.qdrv.stat().st_size,'qualification artifact differs')
    pins_path=module_build_dir/'input-pins.json'; pins=json.loads(pins_path.read_text()); verified_pins={}
    for name,digest in pins.items():
        path=source_path(name); require(sha(path)==digest,'source qualification drift '+name); verified_pins[str(path.resolve())]=digest
    final=DEVICE/'firmware/f372-f371-auc-tqe-observation-device-bound'; require(not final.exists(),'immutable F372 already exists')
    require(sha(SOURCE/'manifest.json')=='211de602dc6291388552a02418a89c80a174359e4e41380d2a9f3a55e5e23842','F371 manifest drift')
    source=json.loads((SOURCE/'manifest.json').read_text()); image=SOURCE/source['artifacts']['webformat']['file']; rootfs=SOURCE/source['artifacts']['rootfs_squashfs']['file']; old=image.name.removesuffix('.webformat.bin')
    require(sha(image)=='b2eb2d0af57b6beaf47981d575ffd769997135fd46179bed8cb4fc3bd00ae147' and image.stat().st_size==5382144,'F371 image drift')
    require(sha(rootfs)==source['artifacts']['rootfs_squashfs']['sha256'],'F371 rootfs drift')
    store_spec=source['preserved_store']; store=Path(store_spec['path']).read_bytes()
    require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'preserved store drift')
    recovery=source['recovery']; fallback=Path(recovery['image']).read_bytes()
    require(sha(recovery['image'])==recovery['sha256'] and crc(fallback+b'\xff'*(0x5e0000-len(fallback))+store)==recovery['full_slot_crc32_with_preserved_store'],'F365 rollback drift')
    paths=[Path(__file__),ROOT/'tools/f372_rootfs_worker.py',ROOT/'tools/build_f367r8_mode_image.py',ROOT/'tools/compose_f164_squashfs_product.py',ROOT/'tools/build_f71_qcsapi_interp_from_f70.py',ROOT/'tools/bootbase_contract_emulator.py',ROOT/'tools/lyoko_web_rootfs_worker.py',ROOT/'tools/f334_shadow_rootfs_worker.py',ROOT/'tools/f334_shadow_contract.py',SOURCE/'manifest.json',SOURCE/'rootfs-inventory.json',SOURCE/'known_hosts.f371',image,rootfs,a.qualification,build_proof_path,comparison_path,pins_path,a.qdrv,Path(store_spec['path']),Path(recovery['image'])]
    paths.extend(SOURCE/(old+suffix) for suffix in FIELDS)
    inputs={str(path.resolve()):sha(path) for path in paths}; inputs.update(verified_pins); build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
    out=DEVICE/'analysis'/('f372-fullimage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')); out.mkdir(parents=True,exist_ok=False)
    refs=dict(complete_qdrv_qualification=item(a.qualification),full_baseline_comparison=item(comparison_path),original_module_build=item(build_proof_path),qualified_qdrv=item(a.qdrv))
    print(json.dumps(dict(build_started=str(out),hardware_actions=False)),flush=True)
    for lane in ('a','b'):
        assets=out/lane/'assets'; assets.mkdir(parents=True); build=out/lane/'build'; inventory=out/lane/'rootfs-inventory.json'
        for suffix,name in FIELDS.items(): shutil.copyfile(SOURCE/(old+suffix),assets/name)
        argv=['wsl.exe','-d',a.distro,'-u','root','-e','python3',linux(ROOT/'tools/f372_rootfs_worker.py'),'--source',linux(rootfs),'--source-sha',sha(rootfs),'--qdrv',linux(a.qdrv),'--qdrv-sha',a.qdrv_sha,'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
        run=subprocess.run(argv,capture_output=True,timeout=900); (out/lane/'worker.stdout').write_bytes(run.stdout); (out/lane/'worker.stderr').write_bytes(run.stderr)
        require(run.returncode==0,'F372 rootfs worker: '+run.stderr.decode(errors='replace')[-2400:])
        saved={key:getattr(compose,key) for key in ('ASSETS','OUT','BASE','ROOTFS_WINDOW','SOURCE_DATE_EPOCH')}; template=compose.f71.TEMPLATE; log=io.StringIO()
        try:
            compose.ASSETS=assets; compose.OUT=build; compose.BASE=BASE; compose.ROOTFS_WINDOW=0x460000; compose.SOURCE_DATE_EPOCH=EPOCH; compose.f71.TEMPLATE=image
            with contextlib.redirect_stdout(log): rc=compose.main()
        finally:
            for key,value in saved.items(): setattr(compose,key,value)
            compose.f71.TEMPLATE=template
        (out/lane/'composition.log').write_text(log.getvalue()); require(rc==0,'composition failed')
        composed=json.loads((build/'manifest.json').read_text()); delta=json.loads(inventory.read_text()); body=(build/(BASE+'.webformat.bin')).read_bytes()
        require(delta['status']=='PASS_F372_OBSERVATION_ROOTFS' and delta['all_other_entries_unchanged'] is True and set(delta['changed_files'])==ALLOWED,'unexpected rootfs delta')
        require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS' and body[64:0x180000]==image.read_bytes()[64:0x180000],'Bootbase or kernel preservation')
        for artifact,suffix in (('kernel_lzma','.kernel.lzma'),('config','.config'),('dtb','.dtb')): require(sha(build/(BASE+suffix))==source['artifacts'][artifact]['sha256'],'kernel/config/DT changed')
        require(delta['before'][WLAN]==delta['after'][WLAN],'F365 WLAN changed')
        prefix=body+b'\xff'*(0x5e0000-len(body)); full=prefix+store; m=copy.deepcopy(source)
        for key in ('layout','kernel','rootfs','artifacts','contracts'): m[key]=composed[key]
        bindings={path:delta['after'][path.lstrip('/')]['sha256'] for path in source['runtime_bindings']}
        require({path for path in bindings if bindings[path]!=source['runtime_bindings'][path]}=={'/'+name for name in ALLOWED},'runtime binding drift')
        m.update(schema='openmitrastar.f372-auc-tqe-observation-image/v1',classification='PRIVATE_NORMAL_NONDFS_F371_WITH_F370_OBSERVATION_NO_PHYSICAL_GO',candidate_eligible=False,flash_supported=False,release_eligible=False,product_version=VERSION,firmware_build_id=build_id,generated_at_utc=datetime.now(timezone.utc).isoformat(),source={'firmware':'F371 exact','image_sha256':sha(image),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},runtime_bindings=bindings,recovery=recovery,preserved_store=store_spec,change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'driver_source':'F370 observation only on exact F365 lineage','driver_contract_and_starter_delta':'ASCII QDRV SHA-256 only','starter_logic_compatibility_wlan_kernel_config_dt_2g_regulatory_calibration_identity_ethernet_unchanged':True,'native_dfs_added':False,'tx_ba_queue_ownership_return_policy_unchanged':True},revision={'scope':'Four saturating read-only AuC TQE result counters; no driver behavior/policy change','previous_manifest_sha256':sha(SOURCE/'manifest.json')},evidence=refs,reproducibility={'qdrv_double_build_qualified':True,'all_other_modules_and_binaries_reused':True,'rootfs_repacked_twice':True,'epoch':EPOCH,'complete_source_release_rebuild':False},physical_validation={'persistent_cold_boot':'UNRUN','control_plane':'UNRUN','client_association':'UNRUN','bidirectional_traffic':'UNRUN','soak':'UNRUN','manual_mtd3_recovery':'UNRUN','release':'UNRUN'},promotion={'offline':'GO','physical':'NO_GO_PENDING_EXACT_ARTIFACT_AUTHORIZATION_AND_CURRENT_GATES'},measurement={'parameters':sorted(PARAMETERS),'permissions':'0444','counter_semantics':'approximate saturating uint; raw OK means consumption, not RF delivery','inflight_tqe_hang_observable':False,'new_per_packet_logs_or_allocations':False},limits=['Normal startup on this candidate remains physically UNRUN.','Counter values are approximate under concurrent callers and do not prove RF delivery.','Counters after tqe_tx cannot observe a call stuck inside its active wait.','No performance, client/traffic, cold boot or recovery acceptance is transferred from another candidate.','No hot reload; F355 lifetime pin is unchanged.'])
        m['normal_5g']['functional_start_physically_verified']=False; m['module_closure']['f370_complete_qdrv_qualification']=item(a.qualification)
        m['layout']['firmware_prefix_crc32']=crc(prefix); m['layout']['physical_firmware_prefix_limit_bytes']=0x5e0000; m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, read-only checksum model; not a flash file'}
        (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n'); shutil.copyfile(inventory,build/'rootfs-inventory.json'); shutil.copyfile(SOURCE/'known_hosts.f371',build/'known_hosts.f372')
        (build/'LAYOUT.md').write_text('# F372 AuC TQE result observation\n\nExact F371 starter logic/compatibility and all components except QDRV remain unchanged. Qualified F370 QDRV adds four read-only counters only. Driver contract and starter ASCII hashes and catalog/release metadata bind exact bytes. Boot/control/client/traffic/cold boot/recovery remain separate physical gates. Protected partitions and store remain unchanged. No device access occurred. OFFLINE GO; physical NO_GO until exact artifact authority and current gates.\n')
        (build/'SHA256SUMS').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in sorted(build.iterdir()) if path.is_file() and path.name!='SHA256SUMS'))
        print(json.dumps(dict(lane=lane,image_sha256=sha(build/(BASE+'.webformat.bin')),image_bytes=len(body),bootbase='PASS')),flush=True)
    for suffix in (*FIELDS,'.rootfs.squashfs','.webformat.bin'): require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
    for path,digest in inputs.items(): require(sha(path)==digest,'input changed during composition')
    shutil.copytree(out/'a/build',final); restrict_acl(final,directory=True)
    for path in final.iterdir():
        if path.is_file(): restrict_acl(path,directory=False)
    m=json.loads((final/'manifest.json').read_text())
    result=dict(schema=m['schema'],status='PASS_OFFLINE_F372_AUC_TQE_OBSERVATION_IMAGE',artifact=item(final/(BASE+'.webformat.bin')),manifest=str(final/'manifest.json'),manifest_sha256=sha(final/'manifest.json'),product_version=VERSION,firmware_build_id=build_id,reproducible=True,bootbase='PASS',slot_fit=True,physical_prefix_fit=True,rootfs_headroom=m['layout']['rootfs_headroom_bytes'],prefix_crc32=m['layout']['firmware_prefix_crc32'],full_slot=m['artifacts']['full_slot'],preserved_store=store_spec,recovery=recovery,runtime_bindings=m['runtime_bindings'],rootfs_changed_files=m['change_scope']['files'],all_inputs_unchanged=True,hardware_actions=False,flash_go_no_go='OFFLINE_GO_NO_GO_PHYSICAL_PENDING_EXACT_AUTHORIZATION_AND_CURRENT_GATES')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(dict(result=str(out/'result.json'),artifact=result['artifact'],manifest=result['manifest'],manifest_sha256=result['manifest_sha256'],status=result['status'],hardware_actions=False),indent=2))

if __name__=='__main__': main()
