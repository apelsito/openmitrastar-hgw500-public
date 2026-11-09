"""Build a new private F369 full image; never access or modify the router."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,contextlib,copy,hashlib,io,json,shutil,subprocess
from build_f367r8_mode_image import compose,restrict_acl,sha,item,linux,crc,require,EPOCH
from f369_rootfs_worker import VERSION,QDRV,NATIVE,CONTRACT,PROFILE,RELEASE,STORAGE,ARTIFACTS_PATH,ALLOWED

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=DEVICE/'firmware/f367r9-f365-transition-observation-device-bound'
EVIDENCE=ROOT/'outputs/rea/arc700-20261021-r2'
BASE='openmitrastar-linux510-f369-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
FIELDS={'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage','.kernel.raw.bin':'kernel-squashfs.raw.bin','.kernel.lzma':'kernel-squashfs.lzma','.config':'kernel-squashfs.config','.dtb':'topaz_mitrastar_squashfs.dtb','.vmlinux':'kernel-squashfs.vmlinux'}

def native_path(path):
    if path.startswith('/mnt/') and len(path)>7 and path[6]=='/': return Path(path[5].upper()+':/'+path[7:])
    return Path(path)

def verify_pins(pins,base=None):
    verified={}
    for name,digest in pins.items():
        path=native_path(name)
        if not path.is_absolute():
            require(base is not None,'relative pin without source base'); path=base/path
        path=path.resolve();require(sha(path)==digest,'source drift '+str(path));verified[str(path)]=digest
    return verified

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--distro',default='REA-Linux');a=parser.parse_args()
    final=DEVICE/'firmware/f369-f367r9-store38-quarantine-device-bound';require(not final.exists(),'immutable F369 already exists')
    components_path=EVIDENCE/'f368r2-module/result.json';components=json.loads(components_path.read_text())
    require(components['status']=='PASS_OFFLINE_QDRV_MODULE' and components['source_revision']=='F368r2' and components['reproducible'] is True,'F368r2 qualification missing')
    require(components['imports_unchanged']==393 and components['exports_unchanged']==15,'F367r9 symbol contract differs')
    qdrv=native_path(components['modules'][0]['path']);require(sha(qdrv)=='01402519e44293b2311c395edf5ae9f56c77a076780669a3b9179fe9af25c240' and qdrv.stat().st_size==703624,'exact F368r2 artifact mismatch')
    for artifact in components['modules']:
        require(sha(native_path(artifact['path']))==sha(qdrv) and native_path(artifact['path']).stat().st_size==703624,'module two-build mismatch')
    source_manifest_path=ROOT/'work/kernel-port/f368r2-txpower-quarantine/source-manifest.json';source_manifest=json.loads(source_manifest_path.read_text())
    module_pins=verify_pins(components['source_pins']);source_pins=verify_pins(source_manifest['source_pins'],source_manifest_path.parent)
    builder_pins=verify_pins(components['builder_pins'])
    replay_path=EVIDENCE/'f368r2-fault-path-r3/result.json';replay=json.loads(replay_path.read_text())
    require(replay['status']=='PASS_OFFLINE_QUARANTINE' and replay['hardware_accessed'] is False and replay['source_delta_verified'] is True and 'cases=16 checks=80 stale_off_confirmation=0 hardware=0' in replay['stdout'],'STORE38 failure replay missing')
    replay_pins=verify_pins(replay['source_pins'])
    rea_path=EVIDENCE/'f368r2-rea-store38/result.json';rea_json=EVIDENCE/'f368r2-rea-store38/rea.json';rea=json.loads(rea_path.read_text())
    require(rea['exit_code']==0 and rea['target_unchanged'] is True and rea['hardware_accessed'] is False and sha(rea_json)==rea['rea_output_sha256'],'REA evidence mismatch')
    rea_target=native_path(rea['command'][3]);require(sha(rea_target)==rea['target_sha256'],'REA derived target drift')
    require(sha(SOURCE/'manifest.json')=='eff3e150b7c9a03d1cac95fe3ffae3fff374180ce0ff58215acf9ff230181858','F367r9 manifest drift')
    source=json.loads((SOURCE/'manifest.json').read_text());image=SOURCE/source['artifacts']['webformat']['file'];rootfs=SOURCE/source['artifacts']['rootfs_squashfs']['file'];old=image.name.removesuffix('.webformat.bin')
    require(sha(image)=='6bf5a08edd5b18adf1597efbd5367d5ad439363c7f7a13a035efc615b4cee440' and image.stat().st_size==5468160,'F367r9 image drift')
    require(sha(rootfs)==source['artifacts']['rootfs_squashfs']['sha256'],'F367r9 rootfs drift')
    require(sha(SOURCE/(old+'.config'))==components['kernel_config_sha256'],'module/kernel config mismatch')
    store_spec=source['preserved_store'];store=Path(store_spec['path']).read_bytes()
    require(len(store)==0x1c0000 and sha(store_spec['path'])==store_spec['sha256'] and crc(store)==store_spec['crc32'],'preserved store drift')
    recovery=source['recovery'];fallback=Path(recovery['image']).read_bytes()
    require(sha(recovery['image'])==recovery['sha256'] and crc(fallback+b'\xff'*(0x5e0000-len(fallback))+store)==recovery['full_slot_crc32_with_preserved_store'],'F365 rollback drift')
    paths=[Path(__file__),ROOT/'tools/f369_rootfs_worker.py',ROOT/'tools/build_f367r8_mode_image.py',ROOT/'tools/compose_f164_squashfs_product.py',ROOT/'tools/build_f71_qcsapi_interp_from_f70.py',ROOT/'tools/bootbase_contract_emulator.py',ROOT/'tools/lyoko_web_rootfs_worker.py',ROOT/'tools/f334_shadow_rootfs_worker.py',ROOT/'tools/f334_shadow_contract.py',components_path,source_manifest_path,replay_path,rea_path,rea_json,rea_target,SOURCE/'manifest.json',rootfs,image,qdrv,Path(store_spec['path']),Path(recovery['image']),SOURCE/'known_hosts.f367']
    paths.extend(SOURCE/(old+suffix) for suffix in FIELDS)
    inputs={str(path.resolve()):sha(path) for path in paths};inputs.update(module_pins);inputs.update(source_pins);inputs.update(builder_pins);inputs.update(replay_pins)
    build_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
    out=DEVICE/'analysis'/('f369-fullimage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
    refs={'qdrv_module_qualification':item(components_path),'store38_fault_replay':item(replay_path),'rea_store38_execution':item(rea_path),'rea_store38_evidence':item(rea_json),'qdrv_source_manifest':item(source_manifest_path)}
    campaign=copy.deepcopy(source['campaign']);campaign.update(runtime_revision='F369',qdrv_source_revision='F368r2',diagnostic_only=True,product_automatic_5g_start=False,store38_ack_normalized=True,store38_published_timeout_descriptor_quarantined=True,store38_descriptor_reclaim='reboot-only',functional_deadlines_unchanged=True,**refs)
    print(json.dumps(dict(build_started=str(out),hardware_actions=False)),flush=True)
    for lane in ('a','b'):
        assets=out/lane/'assets';assets.mkdir(parents=True);build=out/lane/'build';inventory=out/lane/'rootfs-inventory.json'
        for suffix,name in FIELDS.items():shutil.copyfile(SOURCE/(old+suffix),assets/name)
        argv=['wsl.exe','-d',a.distro,'-u','root','-e','python3',linux(ROOT/'tools/f369_rootfs_worker.py'),'--source',linux(rootfs),'--source-sha',sha(rootfs),'--qdrv',linux(qdrv),'--qdrv-sha',sha(qdrv),'--build-id',build_id,'--epoch',str(EPOCH),'--image',linux(assets/'rootfs-product-xz-128k.squashfs'),'--result',linux(inventory)]
        run=subprocess.run(argv,capture_output=True,timeout=900);(out/lane/'worker.stdout').write_bytes(run.stdout);(out/lane/'worker.stderr').write_bytes(run.stderr)
        require(run.returncode==0,'F369 rootfs worker: '+run.stderr.decode(errors='replace')[-2400:])
        saved={key:getattr(compose,key) for key in ('ASSETS','OUT','BASE','ROOTFS_WINDOW','SOURCE_DATE_EPOCH')};template=compose.f71.TEMPLATE;log=io.StringIO()
        try:
            compose.ASSETS=assets;compose.OUT=build;compose.BASE=BASE;compose.ROOTFS_WINDOW=0x460000;compose.SOURCE_DATE_EPOCH=EPOCH;compose.f71.TEMPLATE=image
            with contextlib.redirect_stdout(log):rc=compose.main()
        finally:
            for key,value in saved.items():setattr(compose,key,value)
            compose.f71.TEMPLATE=template
        (out/lane/'composition.log').write_text(log.getvalue());require(rc==0,'composition failed')
        composed=json.loads((build/'manifest.json').read_text());delta=json.loads(inventory.read_text());body=(build/(BASE+'.webformat.bin')).read_bytes()
        require(delta['status']=='PASS_F369_STORE38_ROOTFS' and delta['all_other_entries_unchanged'] is True and set(delta['changed_files'])==ALLOWED,'unexpected rootfs delta')
        require(len(body)<=0x5e0000 and composed['contracts']['bootbase']=='PASS' and body[64:0x180000]==image.read_bytes()[64:0x180000],'Bootbase or kernel preservation')
        prefix=body+b'\xff'*(0x5e0000-len(body));full=prefix+store;m=copy.deepcopy(source)
        for key in ('layout','kernel','rootfs','artifacts','contracts'):m[key]=composed[key]
        bindings={path:delta['after'][path.lstrip('/')]['sha256'] for path in source['runtime_bindings']}
        require({path for path in bindings if bindings[path]!=source['runtime_bindings'][path]}=={'/'+name for name in ALLOWED},'runtime binding drift')
        m.update(schema='openmitrastar.f369-store38-quarantine-image/v1',classification='PRIVATE_DIAGNOSTIC_STORE38_QUARANTINE_NO_PHYSICAL_GO',candidate_eligible=False,product_version=VERSION,firmware_build_id=build_id,generated_at_utc=datetime.now(timezone.utc).isoformat(),source={'firmware':'F367r9 exact','image_sha256':sha(image),'manifest_sha256':sha(SOURCE/'manifest.json'),'inputs':inputs},runtime_bindings=bindings,campaign=campaign,native_dfs=delta['native_profile'],recovery=recovery,preserved_store=store_spec,change_scope={'files':delta['changed_files'],'rootfs':delta['checks'],'driver_source':'F368r2','kernel_wlan_2g_provider_engine_static_helper_supervisor_unchanged':True,'native_helper_only_hash_pins_changed':True},revision={'scope':'STORE38 ACK DONE/ERR normalization plus quarantine of published timeout descriptor; no argument/deadline/regulatory changes','previous_manifest_sha256':sha(SOURCE/'manifest.json')},evidence=refs,reproducibility={'qdrv_build_count':2,'qdrv_byte_identical':True,'other_modules_and_binaries_reused':True,'rootfs_repacked_twice':True,'epoch':EPOCH,'complete_source_release_rebuild':False},physical_validation={'boot':'UNRUN','control_plane':'UNRUN','client_association':'UNRUN','bidirectional_traffic':'UNRUN','RF_CAC_NOP':'UNRUN','release':'UNRUN'},promotion={'offline':'GO','physical':'NO_GO_PENDING_EXACT_ARTIFACT_AUTHORIZATION_AND_CURRENT_GATES'},limits=['Derived REA linked target has synthetic external functions and does not prove target execution.','Failure replay substitutes ring/clock/mailbox and does not prove physical DMA/MuC/RF.','Timed-out STORE38 descriptor is not reclaimed during this boot; repeated failures can exhaust the ring.','Diagnostic activation and native DFS constraints retained; no automatic product 5 GHz startup.'])
        m['module_closure']['f368r2_qdrv_qualification']=item(components_path);m['module_closure']['qdrv_imports_unchanged']=393;m['module_closure']['qdrv_exports_unchanged']=15
        m['layout']['firmware_prefix_crc32']=crc(prefix);m['layout']['physical_firmware_prefix_limit_bytes']=0x5e0000;m['artifacts']['full_slot']={'bytes':len(full),'crc32':crc(full),'sha256':hashlib.sha256(full).hexdigest(),'store_source':'preserved actual journal, not FF padding; read-only checksum model, not flash file'}
        (build/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');shutil.copyfile(inventory,build/'rootfs-inventory.json');shutil.copyfile(SOURCE/'known_hosts.f367',build/'known_hosts.f367')
        (build/'LAYOUT.md').write_text('# F369 STORE38 diagnostic candidate\n\nQDRV is exact F368r2. Only its loader/contract hash and release/profile/catalog metadata change from exact F367r9. Kernel, DTB, WLAN, 2.4 GHz, radar provider, native helper logic, controller, deadlines and regulatory policy remain unchanged. Timed-out STORE38 descriptors remain reserved until reboot. No device access occurred. OFFLINE GO; physical NO_GO until exact artifact authorization, current protection/readback and rollback gates. OEM protected partitions and logical mtd6 are never write targets.\n')
        (build/'SHA256SUMS').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in sorted(build.iterdir()) if path.is_file() and path.name!='SHA256SUMS'))
        print(json.dumps(dict(lane=lane,image_sha256=sha(build/(BASE+'.webformat.bin')),image_bytes=len(body),bootbase='PASS')),flush=True)
    for suffix in (*FIELDS,'.rootfs.squashfs','.webformat.bin'):require(sha(out/'a/build'/(BASE+suffix))==sha(out/'b/build'/(BASE+suffix)),'reproduction mismatch '+suffix)
    for path,digest in inputs.items():require(sha(path)==digest,'input changed during composition')
    shutil.copytree(out/'a/build',final);restrict_acl(final,directory=True)
    for path in final.iterdir():
        if path.is_file():restrict_acl(path,directory=False)
    m=json.loads((final/'manifest.json').read_text())
    result=dict(schema=m['schema'],status='PASS_OFFLINE_F369_STORE38_IMAGE',artifact=item(final/(BASE+'.webformat.bin')),manifest=str(final/'manifest.json'),manifest_sha256=sha(final/'manifest.json'),product_version=VERSION,firmware_build_id=build_id,reproducible=True,bootbase='PASS',slot_fit=True,physical_prefix_fit=True,rootfs_headroom=m['layout']['rootfs_headroom_bytes'],prefix_crc32=m['layout']['firmware_prefix_crc32'],full_slot=m['artifacts']['full_slot'],preserved_store=store_spec,recovery=recovery,runtime_bindings=m['runtime_bindings'],evidence=refs,rootfs_changed_files=m['change_scope']['files'],all_inputs_unchanged=True,hardware_actions=False,flash_go_no_go='OFFLINE_GO_NO_GO_PHYSICAL_PENDING_EXACT_AUTHORIZATION_AND_CURRENT_GATES')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(result=str(out/'result.json'),artifact=result['artifact'],manifest=result['manifest'],manifest_sha256=result['manifest_sha256'],status=result['status'],hardware_actions=False),indent=2))

if __name__=='__main__':main()
