"""Offline complete F373 rootfs integration; refuse composition when oversized."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import contextlib
import hashlib
import io
import json
import shutil
import subprocess

from build_f367r8_mode_image import compose, restrict_acl, sha, item, linux, require, EPOCH
from f373_rootfs_worker import VERSION

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE = DEVICE/'firmware/f372-f371-auc-tqe-observation-device-bound'
GAME = ROOT/'outputs/doom/browser-20261022-r2-touch/www/Doom'
ENGLISH = ROOT/'outputs/doom/english-episode1-20261021T222750344251Z/index.html'
LED = ROOT/'outputs/rea/arc700-20261021-r2/led-cli-candidate-r2-20261021T215300Z/om-ledctl'
RCS = ROOT/'outputs/rea/arc700-20261021-r2/boot-timing-candidate-20261021T215129281623Z/rcS'
ROOTFS_WINDOW, PREFIX, ROOTFS_OFFSET = 0x460000, 0x5e0000, 0x180000
SQUASHFS_TOOL_PINS = {'/usr/bin/mksquashfs':'47d5c1af3da11864e64c9dc6bb4e568719dcc315e6a744e79381ce3374fb7393',
                      '/usr/bin/unsquashfs':'b305985eb764b6d0ef757571e3e44044ebf71c827c4263efe576e9e14b4abcfb'}
BASE = 'openmitrastar-linux510-f373-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
FIELDS = {'.uncompressed.uImage':'kernel-squashfs.uncompressed.uImage',
          '.kernel.raw.bin':'kernel-squashfs.raw.bin', '.kernel.lzma':'kernel-squashfs.lzma',
          '.config':'kernel-squashfs.config', '.dtb':'topaz_mitrastar_squashfs.dtb',
          '.vmlinux':'kernel-squashfs.vmlinux'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--distro', default='REA-Linux')
    a = parser.parse_args()
    require(a.distro == 'REA-Linux', 'pinned build distribution required')
    require(sha(SOURCE/'manifest.json') == 'e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5', 'F372 manifest drift')
    source = json.loads((SOURCE/'manifest.json').read_text())
    image = SOURCE/source['artifacts']['webformat']['file']
    rootfs = SOURCE/source['artifacts']['rootfs_squashfs']['file']
    require(sha(image) == 'e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9'
            and image.stat().st_size == 5382144, 'F372 image drift')
    require(sha(rootfs) == source['artifacts']['rootfs_squashfs']['sha256'], 'F372 rootfs drift')
    for field, suffix in (('kernel_lzma', '.kernel.lzma'), ('config', '.config'), ('dtb', '.dtb')):
        require(sha(SOURCE/(image.name.removesuffix('.webformat.bin')+suffix))
                == source['artifacts'][field]['sha256'], 'F372 kernel/config/DT input drift')
    for ref in (source['preserved_store'], source['recovery']):
        path = Path(ref.get('path', ref.get('image')))
        require(sha(path) == ref['sha256'] and path.stat().st_size == ref['bytes'], 'store or exact F365 return drift')
    require(sha(ENGLISH) == 'f05c849f945e56f4250a7800e627a732e9711746465c8359d5cfeb270d5baa33', 'English page drift')
    require(sha(LED) == '0b2509b8dbd628174b952d6b115c6e6be3a39f89b96514e2f17290fae5e81753', 'LED artifact drift')
    require(sha(RCS) == 'd5870a307ee1514689ca134cb51a25effdc932ccaa715168737cdedf65e30653', 'timing artifact drift')
    files = []
    for path in sorted(GAME.rglob('*')):
        require(not path.is_symlink(), 'game symlink forbidden')
        if path.is_file():
            chosen = ENGLISH if path.relative_to(GAME).as_posix() == 'index.html' else path
            files.append(dict(destination='www/Doom/'+path.relative_to(GAME).as_posix(),
                              path=str(chosen), linux_path=linux(chosen), bytes=chosen.stat().st_size,
                              sha256=sha(chosen), mode=0o644))
    require(len(files) == 10, 'complete exact game file set required')
    for path, destination in ((LED, 'usr/sbin/om-ledctl'), (RCS, 'etc/init.d/rcS')):
        files.append(dict(destination=destination, path=str(path), linux_path=linux(path),
                          bytes=path.stat().st_size, sha256=sha(path), mode=0o755))
    original_base = image.name.removesuffix('.webformat.bin')
    toolpaths = [Path(__file__), ROOT/'tools/f373_rootfs_worker.py', ROOT/'tools/lyoko_web_rootfs_worker.py',
                 ROOT/'tools/f334_shadow_rootfs_worker.py', ROOT/'tools/f334_shadow_contract.py',
                 ROOT/'tools/build_f367r8_mode_image.py', ROOT/'tools/compose_f164_squashfs_product.py',
                 ROOT/'tools/build_f71_qcsapi_interp_from_f70.py', ROOT/'tools/bootbase_contract_emulator.py',
                 SOURCE/'manifest.json', SOURCE/'rootfs-inventory.json', image, rootfs]
    toolpaths.extend(SOURCE/(original_base+suffix) for suffix in FIELDS)
    toolpaths.extend(Path(row['path']) for row in files)
    toolpaths.extend(Path(ref.get('path', ref.get('image')))
                     for ref in (source['preserved_store'], source['recovery']))
    pins = {str(path.resolve()): sha(path) for path in toolpaths}
    build_id = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()[:16]
    out = DEVICE/'analysis'/('f373-doom-led-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    restrict_acl(out, directory=True)
    manifest = dict(schema='openmitrastar.f373-offline-inputs/v1', version=VERSION,
                    source_firmware='F372 exact', source_pins=pins, files=files,
                    expected_parent_led_sha256='0df28604268964c7a99c26f831d94d4e7ae1a06bce86189b1bb97567ae711b47',
                    expected_parent_rcs_sha256='2435abe03da459ff82f8ca77bf2a447f30c043c9e69c6da1a411702dfafc0592',
                    hardware_actions=False)
    input_path = out/'inputs.json'
    input_path.write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(build_started=str(out), hardware_actions=False)), flush=True)
    runtime = subprocess.run(['wsl.exe', '-d', a.distro, '-u', 'root', '-e', 'sh', '-c',
                              'sha256sum /usr/bin/mksquashfs /usr/bin/unsquashfs; mksquashfs -version'],
                             capture_output=True, timeout=30)
    require(runtime.returncode == 0, 'SquashFS runtime identification failed')
    observed_tools = {line.split('  ', 1)[1]:line.split('  ', 1)[0]
                      for line in runtime.stdout.decode().splitlines()[:2]}
    require(observed_tools == SQUASHFS_TOOL_PINS, 'pinned SquashFS binaries changed')
    (out/'squashfs-runtime.txt').write_bytes(runtime.stdout)
    rows = []
    for lane in ('a', 'b'):
        lane_out = out/lane
        lane_out.mkdir()
        packed = lane_out/'F373-ANALYSIS-ONLY-NOT-A-FLASH-IMAGE.squashfs'
        inventory = lane_out/'rootfs-inventory.json'
        command = ['wsl.exe', '-d', a.distro, '-u', 'root', '-e', 'python3',
                   linux(ROOT/'tools/f373_rootfs_worker.py'), '--source', linux(rootfs),
                   '--source-sha', sha(rootfs), '--input-manifest', linux(input_path),
                   '--input-manifest-sha', sha(input_path), '--build-id', build_id,
                   '--epoch', str(EPOCH), '--image', linux(packed), '--result', linux(inventory)]
        worker = subprocess.run(command, capture_output=True, timeout=900)
        (lane_out/'worker.stdout').write_bytes(worker.stdout)
        (lane_out/'worker.stderr').write_bytes(worker.stderr)
        require(worker.returncode == 0, 'F373 rootfs worker failed '+worker.stderr.decode(errors='replace')[-1200:])
        row = json.loads(inventory.read_text())
        require(row['all_other_entries_unchanged'] and row['image_sha256'] == sha(packed), 'F373 verified inventory failed')
        rows.append(dict(lane=lane, rootfs=item(packed), inventory=item(inventory),
                         changed_files=row['changed_files'], catalogs_after=row['catalogs_after']))
        print(json.dumps(dict(lane=lane, rootfs_bytes=packed.stat().st_size, sha256=sha(packed))), flush=True)
    require(rows[0]['rootfs']['sha256'] == rows[1]['rootfs']['sha256'], 'double rootfs reproduction differs')
    require(rows[0]['changed_files'] == rows[1]['changed_files'], 'double delta differs')
    for path, digest in pins.items():
        require(sha(path) == digest, 'source changed during F373 integration')
    runtime_after = subprocess.run(['wsl.exe', '-d', a.distro, '-u', 'root', '-e', 'sh', '-c',
                                    'sha256sum /usr/bin/mksquashfs /usr/bin/unsquashfs'],
                                   capture_output=True, timeout=30)
    require(runtime_after.returncode == 0 and runtime_after.stdout.decode().splitlines()
            == runtime.stdout.decode().splitlines()[:2], 'SquashFS tools changed during packing')
    size = rows[0]['rootfs']['bytes']
    fit = size <= ROOTFS_WINDOW and ROOTFS_OFFSET+size <= PREFIX
    result = dict(schema='openmitrastar.f373-doom-led-analysis/v1',
                  status='NO_GO_SLOT_FIT' if not fit else 'OFFLINE_ROOTFS_FIT_PENDING_COMPOSITION',
                  classification='PRIVATE_ANALYSIS_ROOTFS_NOT_FLASH_ARTIFACT', version=VERSION,
                  build_id=build_id, lanes=rows, reproducible_rootfs=True, all_inputs_unchanged=True,
                  source_pins=pins, squashfs_tool_pins=SQUASHFS_TOOL_PINS,
                  squashfs_tools_unchanged=True, input_manifest=item(input_path), rootfs_bytes=size,
                  rootfs_window_bytes=ROOTFS_WINDOW, rootfs_overflow_bytes=max(0, size-ROOTFS_WINDOW),
                  prefix_bytes=PREFIX, rootfs_offset_bytes=ROOTFS_OFFSET,
                  projected_unpadded_image_bytes=ROOTFS_OFFSET+size,
                  projected_prefix_overflow_bytes=max(0, ROOTFS_OFFSET+size-PREFIX),
                  game_input_bytes=sum(row['bytes'] for row in files if row['destination'].startswith('www/Doom/')),
                  complete_game_files=10, hardware_actions=False, flash_artifact_created=False,
                  source_f372_unchanged=True, recovery=source['recovery'],
                  preserved_store=source['preserved_store'], physical_go=False, release_pass=False,
                  limits=['Analysis rootfs includes device identity and remains private.',
                          'Oversized rootfs is not a flash image; no Bootbase webformat is created.',
                          'Physical prefix/store geometry is fixed, protected partitions are not capacity.',
                          'Fresh manual mtd3 recovery and exact artifact authority remain required.',
                          'No performance, client, persistence, traffic or release acceptance is inferred.'])
    if fit:
        # Retain original compositor and exact kernel only if all fit gates pass.
        assets = out/'composition-assets'
        assets.mkdir()
        for suffix, name in FIELDS.items():
            shutil.copyfile(SOURCE/(original_base+suffix), assets/name)
        shutil.copyfile(Path(rows[0]['rootfs']['path']), assets/'rootfs-product-xz-128k.squashfs')
        saved = {key:getattr(compose, key) for key in ('ASSETS', 'OUT', 'BASE', 'ROOTFS_WINDOW', 'SOURCE_DATE_EPOCH')}
        template = compose.f71.TEMPLATE
        log = io.StringIO()
        try:
            compose.ASSETS, compose.OUT, compose.BASE = assets, out/'composition', BASE
            compose.ROOTFS_WINDOW, compose.SOURCE_DATE_EPOCH = ROOTFS_WINDOW, EPOCH
            compose.f71.TEMPLATE = image
            with contextlib.redirect_stdout(log):
                code = compose.main()
        finally:
            for key, value in saved.items():
                setattr(compose, key, value)
            compose.f71.TEMPLATE = template
        (out/'composition.log').write_text(log.getvalue())
        require(code == 0, 'F373 composition failed')
        result['flash_artifact_created'] = True
        result['status'] = 'OFFLINE_IMAGE_FIT_PHYSICAL_NO_GO'
        result['artifact'] = item(out/'composition'/(BASE+'.webformat.bin'))
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(status=result['status'], result=str(out/'result.json'), rootfs_bytes=size,
                          rootfs_overflow_bytes=result['rootfs_overflow_bytes'], hardware_actions=False)), flush=True)


if __name__ == '__main__':
    main()
