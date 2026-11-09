"""Compose only a new F363r2 startup-owner fix; no kernel/module rebuild or HW."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import contextlib
import copy
import hashlib
import io
import json
import shutil
import subprocess
import zlib

import compose_f164_squashfs_product as compose
from init_lyoko_device_host_key import restrict_acl
from f363r2_rootfs_worker import VERSION, OLD_START_SHA, OLD_GATE, NEW_GATE

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
BASE = 'openmitrastar-linux510-f363r2-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
EPOCH = 1790006400


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linux(path):
    path = Path(path).resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]


def crc(data):
    return f'{zlib.crc32(data)&0xffffffff:08x}'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--f363-image-result', type=Path, required=True)
    args = ap.parse_args()
    assert shutil.disk_usage(ROOT).free > 500*1024*1024
    proof = json.loads(args.f363_image_result.read_text())
    assert proof['schema'] == 'openmitrastar.f363-temperature-image/v1'
    assert proof['artifact']['sha256'] == 'c8d49e9d44ff86e5045d4a28aa2e0a90dd68e8bb89c7fc3104f0b874e37ea26d'
    image = Path(proof['artifact']['path']); source_dir = image.parent
    old = image.name.removesuffix('.webformat.bin')
    assert sha(image) == proof['artifact']['sha256'] and image.stat().st_size == proof['artifact']['bytes']
    assert sha(source_dir/'manifest.json') == proof['manifest_sha256']
    source = json.loads((source_dir/'manifest.json').read_text())
    store_spec = proof['preserved_store']; store = Path(store_spec['path']).read_bytes()
    assert len(store) == 0x1c0000 and sha(store_spec['path']) == store_spec['sha256'] and crc(store) == store_spec['crc32']
    recovery = source['recovery']
    assert recovery['version'] == 'lyoko-foundation-6.9.10-f362-dual-ethernet-device'
    assert sha(recovery['image']) == recovery['sha256']
    final = DEVICE/'firmware/f363r2-f363-temperature-owner-device-bound'
    assert not final.exists(), 'immutable F363r2 directory already exists'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = DEVICE/'analysis'/('f363r2-fullimage-'+stamp); out.mkdir(parents=True, exist_ok=False)
    input_paths = (Path(__file__), ROOT/'tools/f363r2_rootfs_worker.py', args.f363_image_result,
                   source_dir/'manifest.json', Path(store_spec['path']))
    inputs = {str(path): sha(path) for path in input_paths}
    build_id = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]
    fields = {'.uncompressed.uImage': 'kernel-squashfs.uncompressed.uImage', '.kernel.raw.bin': 'kernel-squashfs.raw.bin',
              '.kernel.lzma': 'kernel-squashfs.lzma', '.config': 'kernel-squashfs.config',
              '.dtb': 'topaz_mitrastar_squashfs.dtb', '.vmlinux': 'kernel-squashfs.vmlinux'}
    print(json.dumps(dict(build_started=str(out), hardware_actions=False)), flush=True)
    for lane in ('a', 'b'):
        assets = out/lane/'assets'; assets.mkdir(parents=True); build = out/lane/'build'
        inventory = out/lane/'rootfs-inventory.json'
        for suffix, target in fields.items():
            shutil.copyfile(source_dir/(old+suffix), assets/target)
        argv = ['wsl.exe', '-d', 'podman-mem9-tidb', '-u', 'root', '-e', 'python3',
                linux(ROOT/'tools/f363r2_rootfs_worker.py'), '--source', linux(source_dir/(old+'.rootfs.squashfs')),
                '--source-sha', source['artifacts']['rootfs_squashfs']['sha256'], '--build-id', build_id,
                '--epoch', str(EPOCH), '--image', linux(assets/'rootfs-product-xz-128k.squashfs'), '--result', linux(inventory)]
        run = subprocess.run(argv, capture_output=True, timeout=900)
        (out/lane/'worker.stdout').write_bytes(run.stdout); (out/lane/'worker.stderr').write_bytes(run.stderr)
        assert run.returncode == 0, run.stderr.decode(errors='replace')[-1800:]
        settings = dict(ASSETS=assets, OUT=build, BASE=BASE, ROOTFS_WINDOW=0x460000, SOURCE_DATE_EPOCH=EPOCH)
        saved = {key: getattr(compose, key) for key in settings}; template = compose.f71.TEMPLATE; log = io.StringIO()
        try:
            for key, value in settings.items():
                setattr(compose, key, value)
            compose.f71.TEMPLATE = image
            with contextlib.redirect_stdout(log):
                code = compose.main()
        finally:
            compose.f71.TEMPLATE = template
            for key, value in saved.items():
                setattr(compose, key, value)
        (out/lane/'composition.log').write_text(log.getvalue()); assert code == 0
        composed = json.loads((build/'manifest.json').read_text()); delta = json.loads(inventory.read_text())
        body = (build/(BASE+'.webformat.bin')).read_bytes()
        assert len(body) <= 0x5e0000 and composed['contracts']['bootbase'] == 'PASS'
        prefix = body+b'\xff'*(0x5e0000-len(body)); full = prefix+store
        manifest = copy.deepcopy(source)
        for name in ('layout', 'kernel', 'rootfs', 'artifacts', 'contracts'):
            manifest[name] = composed[name]
        manifest.update(schema='openmitrastar.f363r2-temperature-owner-image/v1',
            classification='F363_PRELOADED_TEMPERATURE_ADMISSION_FIX', product_version=VERSION,
            firmware_build_id=build_id, generated_at_utc=stamp, candidate_eligible=True,
            release_eligible=False, flash_supported=False,
            source=dict(firmware='exact F363 c8d49e image; physical platform rejected radio5 startup',
                        image_sha256=sha(image), manifest_sha256=sha(source_dir/'manifest.json'), inputs=inputs),
            change_scope=dict(files=delta['changed_files'], rootfs=delta['checks'],
                kernel_config_dt='byte-identical F363', all_modules='byte-identical F363',
                inherited_f363=source['change_scope'],
                fix='S16-owned temp_sens admitted only after hwmon/temp_sens presence and original named/version363 node validation',
                other_dirty_module_rejections_preserved=True, no_sensor_mmio_added=True),
            startup_admission=dict(old_start_sha256=OLD_START_SHA,
                old_gate_sha256=hashlib.sha256(OLD_GATE.encode()).hexdigest(),
                new_gate_sha256=hashlib.sha256(NEW_GATE.encode()).hexdigest(), tests=delta['tests']),
            preserved_store=store_spec, recovery=recovery,
            reproducibility=dict(kernel_recompiled=False, modules_recompiled=False, rootfs_repacked_twice=True, epoch=EPOCH),
            physical_validation=dict(status='NOT_RUN', temperature_activation='UNRUN', wifi_tests='DEFERRED',
                previous_f363='platform rejected S55-radio5-ap; software admission incompatibility reproduced offline'),
            safety=dict(hardware_actions=False, write_prefix_bytes=0x5e0000, firmware_erase_end_exclusive='0xdc0000',
                normal_write_target='physical mtd4/linux_live at 0x7e0000', protected_partitions=['mtd0','mtd1','mtd2','mtd3','mtd5'],
                startup_sensor_mmio=False, startup_flash_writes=False, automatic_arm=False, automatic_reboot=False,
                flash_go_no_go='OFFLINE_GO_PHYSICAL_INSTALLER_AND_TEMPERATURE_GATE_PENDING'))
        manifest['layout']['firmware_prefix_crc32'] = crc(prefix)
        manifest['artifacts']['full_slot'] = dict(bytes=len(full), crc32=crc(full), sha256=hashlib.sha256(full).hexdigest(),
                                                store_source='preserved actual sequence2 journal, not FF')
        (build/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')
        shutil.copyfile(inventory, build/'rootfs-inventory.json')
        shutil.copyfile(source_dir/'known_hosts.f363', build/'known_hosts.f363')
        (build/'LAYOUT.md').write_text('# F363r2 temperature owner admission\n\nOnly the startup admission and version/catalog metadata differ from F363. All kernel and module bytes are unchanged. S16 registers the disabled sensor before S55; S55 accepts only the expected hwmon and version363 node. Unknown/other preloaded radio modules remain rejected. No sensor MMIO is requested by admission. Physical acceptance is pending; recovery uses actual F362, not failed F363.\n')
        (build/'SHA256SUMS').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in sorted(build.iterdir())
                                                  if path.is_file() and path.name != 'SHA256SUMS'))
    for suffix in (*fields, '.rootfs.squashfs', '.webformat.bin'):
        assert sha(out/'a/build'/(BASE+suffix)) == sha(out/'b/build'/(BASE+suffix)), suffix
    assert (out/'a/rootfs-inventory.json').read_bytes() == (out/'b/rootfs-inventory.json').read_bytes()
    for path, digest in inputs.items():
        assert sha(path) == digest
    shutil.copytree(out/'a/build', final); restrict_acl(final, directory=True)
    for path in final.iterdir():
        if path.is_file():
            restrict_acl(path, directory=False)
    manifest = json.loads((final/'manifest.json').read_text()); candidate = final/(BASE+'.webformat.bin')
    result = dict(schema='openmitrastar.f363r2-temperature-owner-image/v1', status='PASS_OFFLINE_TEMPERATURE_OWNER_IMAGE',
        artifact=dict(path=str(candidate), bytes=candidate.stat().st_size, sha256=sha(candidate)), manifest_sha256=sha(final/'manifest.json'),
        product_version=VERSION, firmware_build_id=build_id, kernel_build='#358', kernel_result=proof['kernel_result'],
        f363_image_result=str(args.f363_image_result), kernel_config_dt_byte_identical_f363=True, all_modules_byte_identical_f363=True,
        reproducible_rootfs_and_image=True, bootbase='PASS', slot_fit=True, prefix_crc32=manifest['layout']['firmware_prefix_crc32'],
        full_slot=manifest['artifacts']['full_slot'], preserved_store=store_spec, rootfs_changed_files=manifest['change_scope']['files'],
        admission_tests=manifest['startup_admission']['tests'], default_sensor_mmio=False,
        default_temperature_state=dict(enabled=0, activation_attempted=0, activation_error=-19), hardware_actions=False,
        recovery=recovery, flash_go_no_go=manifest['safety']['flash_go_no_go'])
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({**result, 'result': str(out/'result.json')}, indent=2))


if __name__ == '__main__':
    main()
