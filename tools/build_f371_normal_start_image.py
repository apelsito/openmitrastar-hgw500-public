"""Compose F371 normal-start compatibility on exact F365, offline only."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess
from build_f367r8_mode_image import compose,restrict_acl,sha,item,linux,crc,require,EPOCH
from f371_rootfs_worker import VERSION,START,HEAD,TAIL,ALLOWED,ARTIFACTS_PATH,QDRV,WLAN
from f334_shadow_contract import parse_artifact_catalog

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f365-f364r3-temperature-data-device-bound'
RAM=ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3'
BASE='openmitrastar-linux510-f371-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
FIELDS={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--distro',default='REA-Linux'); a=p.parse_args()
    final=DEVICE/'firmware/f371-f365-normal-start-compat-device-bound'; require(not final.exists(),'immutable F371 already exists')
    require(sha(SOURCE/'manifest.json')=='a73a41e32d793a33ec13c46ef62bbf5890039339d38ef107d04c13b91e19d19c','F365 manifest drift')
    source=json.loads((SOURCE/'manifest.json').read_text()); image=SOURCE/source['artifacts']['webformat']['file']; rootfs=SOURCE/source['artifacts']['rootfs_squashfs']['file']; old=image.name.removesuffix('.webformat.bin')
    require(sha(image)=='43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355' and image.stat().st_size==5382144,'F365 image drift')
    require(sha(rootfs)=='80a650356f5a45aecb8950a91783e9e4c6d2b591f480988fb44c687ee07914c3','F365 rootfs drift')
    ram=json.loads((RAM/'manifest.json').read_text()); verification=json.loads((RAM/'verification.json').read_text())
    require(ram['status']=='PASS_OFFLINE_RAM_PACKAGE' and ram['hardware_actions'] is False,'compatibility donor unqualified')
    for name in ('head','tail'):
        helper=RAM/'payload/bin'/name; require(sha(helper)==ram['files']['bin/'+name]['sha256'] and helper.stat().st_size==ram['files']['bin/'+name]['bytes'],'RAM helper drift '+name)
    store_spec=source['preserved_store']; store=Path(store_spec['path']).read_bytes()
    require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'preserved store drift')
    fallback=image.read_bytes(); fallback_prefix=fallback+b'\xff'*(0x5e0000-len(fallback)); fallback_full=fallback_prefix+store
    require(crc(fallback_full)=='118901d4' and hashlib.sha256(fallback_full).hexdigest()==source['artifacts']['full_slot']['sha256'],'exact F365 recovery checksum drift')
    recovery=dict(image=str(image),sha256=sha(image),bytes=len(fallback),version=source['product_version'],kernel_build='#358',prefix_crc32=crc(fallback_prefix),full_slot_crc32_with_preserved_store=crc(fallback_full),store_must_be_preserved=True,physical_baseline_and_recovery_acceptance='UNRUN_FOR_F371; root physical installer must bind current known-good rollback')
    paths=[Path(__file__),ROOT/'tools/f371_rootfs_worker.py',ROOT/'tools/build_f367r8_mode_image.py',ROOT/'tools/compose_f164_squashfs_product.py',ROOT/'tools/build_f71_qcsapi_interp_from_f70.py',ROOT/'tools/bootbase_contract_emulator.py',ROOT/'tools/lyoko_web_rootfs_worker.py',ROOT/'tools/f334_shadow_rootfs_worker.py',ROOT/'tools/f334_shadow_contract.py',SOURCE/'manifest.json',SOURCE/'rootfs-inventory.json',SOURCE/'known_hosts.f365',image,rootfs,RAM/'manifest.json',RAM/'verification.json',RAM/'payload/bin/head',RAM/'payload/bin/tail',RAM/'payload/donor/om-radio5-start',Path(store_spec['path'])]
    paths.extend(SOURCE/(old+suffix) for suffix in FIELDS)
    inputs={str(path.resolve()):sha(path) for path in paths}; build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
    out=DEVICE/'analysis'/('f371-fullimage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')); out.mkdir(parents=True,exist_ok=False)
    refs=dict(compatibility_ram_package=item(RAM/'manifest.json'),compatibility_offline_verification=item(RAM/'verification.json'))
    print(json.dumps(dict(build_started=str(out),hardware_actions=False)),flush=True)
    for lane in ('a','b'):
        assets=out/lane/'assets'; assets.mkdir(parents=True); build=out/lane/'build'; inventory=out/lane/'rootfs-inventory.json'
        for suffix,name in FIELDS.items(): shutil.copyfile(SOURCE/(old+suffix),assets/name)
        argv=['wsl.exe','-d',a.distro,'-u','root','-e','python3',linux(ROOT/'tools/f371_rootfs_worker.py'),'--source',linux(rootfs),'--source-sha',sha(rootfs),'--head',linux(RAM/'payload/bin/head'),'--head-sha',sha(RAM/'payload/bin/head'),'--tail',linux(RAM/'payload/bin/tail'),'--tail-sha',sha(RAM/'payload/bin/tail'),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
        run=subprocess.run(argv,capture_output=True,timeout=900); (out/lane/'worker.stdout').write_bytes(run.stdout); (out/lane/'worker.stderr').write_bytes(run.stderr)
        require(run.returncode==0,'F371 rootfs worker: '+run.stderr.decode(errors='replace')[-2400:])
        saved={key:getattr(compose,key) for key in ('ASSETS','OUT','BASE','ROOTFS_WINDOW','SOURCE_DATE_EPOCH')}; template=compose.f71.TEMPLATE; log=io.StringIO()
        try:
            compose.ASSETS=assets; compose.OUT=build; compose.BASE=BASE; compose.ROOTFS_WINDOW=0x460000; compose.SOURCE_DATE_EPOCH=EPOCH; compose.f71.TEMPLATE=image
            with contextlib.redirect_stdout(log): rc=compose.main()
        finally:
            for key,value in saved.items(): setattr(compose,key,value)
            compose.f71.TEMPLATE=template
        (out/lane/'composition.log').write_text(log.getvalue()); require(rc==0,'composition failed')
        composed=json.loads((build/'manifest.json').read_text()); delta=json.loads(inventory.read_text()); body=(build/(BASE+'.webformat.bin')).read_bytes()
        require(delta['status']=='PASS_F371_NORMAL_START_COMPAT_ROOTFS' and delta['all_other_entries_unchanged'] is True and set(delta['changed_files'])==ALLOWED,'unexpected rootfs delta')
        require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS' and body[64:0x180000]==image.read_bytes()[64:0x180000],'Bootbase or kernel preservation')
        for artifact,suffix in (('kernel_lzma','.kernel.lzma'),('config','.config'),('dtb','.dtb')): require(sha(build/(BASE+suffix))==source['artifacts'][artifact]['sha256'],'kernel/config/DT changed')
        require(delta['before'][QDRV]==delta['after'][QDRV] and delta['before'][WLAN]==delta['after'][WLAN],'F365 driver changed')
        prefix=body+b'\xff'*(0x5e0000-len(body)); full=prefix+store; m=copy.deepcopy(source)
        for key in ('layout','kernel','rootfs','artifacts','contracts'): m[key]=composed[key]
        binding_names={name for name,row in delta['after'].items() if row['type']=='file' and (name.startswith('lib/modules/') or name.startswith('etc/init.d/') or name.startswith('etc/openmitrastar/features/') or name in ALLOWED or name in ('usr/share/openmitrastar/radio5g/driver-contract.env','usr/sbin/om-radio5-stop'))}
        bindings={'/'+name:delta['after'][name]['sha256'] for name in sorted(binding_names)}
        m.update(schema='openmitrastar.f371-normal-start-compat-image/v1',classification='PRIVATE_NORMAL_NONDFS_F365_COMPATIBILITY_BASELINE_NO_PHYSICAL_GO',candidate_eligible=False,flash_supported=False,release_eligible=False,product_version=VERSION,firmware_build_id=build_id,generated_at_utc=datetime.now(timezone.utc).isoformat(),source={'firmware':'F365 exact','image_sha256':sha(image),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},runtime_bindings=bindings,recovery=recovery,preserved_store=store_spec,change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'driver_source':'F365 unchanged','normal_starter_delta':'PATH adds exact proven RAM head/tail helpers at /usr/libexec/openmitrastar/f371-compat','qdrv_wlan_kernel_config_dt_2g_regulatory_calibration_identity_ethernet_unchanged':True,'s55_init_and_existing_autostart_feature_unchanged':True,'native_dfs_added':False,'tx_ba_policy_unchanged':True},revision={'scope':'normal non-DFS startup utility compatibility only; no driver or RF/queue policy change','previous_manifest_sha256':sha(SOURCE/'manifest.json')},evidence=refs,reproducibility={'driver_or_kernel_compiled':False,'all_modules_and_binaries_reused':True,'rootfs_repacked_twice':True,'epoch':EPOCH,'complete_source_release_rebuild':False},physical_validation={'persistent_cold_boot':'UNRUN','control_plane':'UNRUN','client_association':'UNRUN','bidirectional_traffic':'UNRUN','soak':'UNRUN','manual_mtd3_recovery':'UNRUN','release':'UNRUN'},promotion={'offline':'GO','physical':'NO_GO_PENDING_EXACT_ARTIFACT_AUTHORIZATION_AND_CURRENT_GATES'},normal_5g={'starter_lineage':'exact F365 with PATH-only change','init_service_and_feature':'byte-identical F365','channel':36,'bandwidth_mhz':80,'security':'preserved existing secure WPA2 settings','functional_start_physically_verified':False,'qdrv_lifetime':'pinned after mutation; no reload'},limits=['Compatible startup does not prove persistent autostart on hardware.','No current physical client association, traffic, cold boot or recovery evidence is transferred to this candidate.','The unchanged F365 driver disables TX BA; maximum performance remains unproven.','Inherited sensor is disabled; no thermal/radar activation is added.'])
        m['layout']['firmware_prefix_crc32']=crc(prefix); m['layout']['physical_firmware_prefix_limit_bytes']=0x5e0000; m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, read-only checksum model; not a flash file'}
        (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n'); shutil.copyfile(inventory,build/'rootfs-inventory.json'); shutil.copyfile(SOURCE/'known_hosts.f365',build/'known_hosts.f371')
        (build/'LAYOUT.md').write_text('# F371 normal-start compatibility baseline\n\nExact F365 kernel/config/DT and all drivers remain unchanged. Only starter PATH, the two proven awk helpers, release identity and required catalogs change. F365 S55 and the existing normal-start feature are preserved; hardware autostart remains UNRUN. Protected partitions and store are unchanged. No device access occurred. OFFLINE GO; physical NO_GO until exact artifact authority and current write/readback/recovery gates.\n')
        (build/'SHA256SUMS').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in sorted(build.iterdir()) if path.is_file() and path.name!='SHA256SUMS'))
        print(json.dumps(dict(lane=lane,image_sha256=sha(build/(BASE+'.webformat.bin')),image_bytes=len(body),bootbase='PASS')),flush=True)
    for suffix in (*FIELDS,'.rootfs.squashfs','.webformat.bin'): require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
    for path,digest in inputs.items(): require(sha(path)==digest,'input changed during composition')
    shutil.copytree(out/'a/build',final); restrict_acl(final,directory=True)
    for path in final.iterdir():
        if path.is_file(): restrict_acl(path,directory=False)
    m=json.loads((final/'manifest.json').read_text())
    result=dict(schema=m['schema'],status='PASS_OFFLINE_F371_NORMAL_START_COMPAT_IMAGE',artifact=item(final/(BASE+'.webformat.bin')),manifest=str(final/'manifest.json'),manifest_sha256=sha(final/'manifest.json'),product_version=VERSION,firmware_build_id=build_id,reproducible=True,bootbase='PASS',slot_fit=True,physical_prefix_fit=True,rootfs_headroom=m['layout']['rootfs_headroom_bytes'],prefix_crc32=m['layout']['firmware_prefix_crc32'],full_slot=m['artifacts']['full_slot'],preserved_store=store_spec,recovery=recovery,runtime_bindings=m['runtime_bindings'],rootfs_changed_files=m['change_scope']['files'],all_inputs_unchanged=True,hardware_actions=False,flash_go_no_go='OFFLINE_GO_NO_GO_PHYSICAL_PENDING_EXACT_AUTHORIZATION_AND_CURRENT_GATES')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(dict(result=str(out/'result.json'),artifact=result['artifact'],manifest=result['manifest'],manifest_sha256=result['manifest_sha256'],status=result['status'],hardware_actions=False),indent=2))

if __name__=='__main__': main()
