"""Measure one TLS-binary substitution in exact F372; no firmware or device I/O."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST_SHA = 'e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5'
SOURCE_ROOTFS_SHA = 'fdffe1ad2798fb8938a847bcc1736fe370cd017a1a71c90b66097aaeac5441b6'
SOURCE_IMAGE_SHA = 'e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9'
TLS_PATH = 'usr/sbin/mini_httpd-tls'
OLD_TLS_SHA = '2a366556ee9ff59b590efc685fcfd5232e64845f2a3ce84244ec4b42b0433d9f'
NEW_TLS_SHA = 'b105f5c80010b2cb09120e9c7b6dbee0cd2f4ea67be9834d66015f96b0102575'
TOOL_PINS = {'/usr/bin/mksquashfs': '47d5c1af3da11864e64c9dc6bb4e568719dcc315e6a744e79381ce3374fb7393',
             '/usr/bin/unsquashfs': 'b305985eb764b6d0ef757571e3e44044ebf71c827c4263efe576e9e14b4abcfb'}
EPOCH = 1790006400
ROOTFS_WINDOW = 0x460000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    return {'path': str(path), 'bytes': Path(path).stat().st_size, 'sha256': sha(path)}


def linux(path):
    path = Path(path).resolve()
    return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]


def require(value, reason):
    if not value:
        raise ValueError(reason)


def check_tools():
    observed = {path: sha(path) for path in TOOL_PINS}
    require(observed == TOOL_PINS, 'SquashFS tool drift')


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def worker(args):
    import lyoko_web_rootfs_worker as web
    from f373_rootfs_worker import catalog_rows, verify_catalogs
    require(os.name == 'posix' and os.geteuid() == 0, 'root Linux worker required')
    spec = json.loads(args.spec.read_text())
    require(spec['hardware_actions'] is False, 'offline scope required')
    for path, digest in spec['linux_pins'].items():
        require(sha(path) == digest, 'input changed: ' + path)
    check_tools()
    source = Path(spec['source_rootfs'])
    out = args.spec.parent
    packed_base = out/'F372-CONTROL-REPACK-ANALYSIS-ONLY.squashfs'
    packed_new = out/'F372-TLS-SUBSTITUTION-ANALYSIS-ONLY.squashfs'
    require(not packed_base.exists() and not packed_new.exists(), 'immutable outputs exist')
    with tempfile.TemporaryDirectory(prefix='f372-tls-size-', dir='/tmp') as scratch:
        root = Path(scratch)/'root'
        subprocess.run(['unsquashfs', '-processors', '1', '-no-progress', '-d', str(root), str(source)],
                       check=True, stdout=subprocess.DEVNULL)
        before = web.inventory(root)
        source_inventory = json.loads(Path(spec['source_inventory']).read_text())['after']
        require(before == source_inventory, 'F372 complete source inventory mismatch')
        require(before[TLS_PATH]['sha256'] == OLD_TLS_SHA and before[TLS_PATH]['bytes'] == 1300436,
                'old TLS substitution target mismatch')
        catalogs = sorted(name for name, row in before.items()
                          if row['type'] == 'file' and name.startswith('usr/share/openmitrastar/')
                          and name.endswith('/artifacts.sha256'))
        catalog_checks_before = verify_catalogs(root, catalogs)
        options = ['-noappend', '-all-root', '-comp', 'xz', '-b', '131072', '-no-xattrs',
                   '-no-exports', '-all-time', str(EPOCH), '-mkfs-time', str(EPOCH),
                   '-processors', '1', '-no-progress']

        def pack_and_check(destination, expected, lane):
            subprocess.run(['mksquashfs', str(root), str(destination), *options],
                           check=True, stdout=subprocess.DEVNULL)
            verified = Path(scratch)/lane
            subprocess.run(['unsquashfs', '-processors', '1', '-no-progress', '-d', str(verified), str(destination)],
                           check=True, stdout=subprocess.DEVNULL)
            after = web.inventory(verified)
            require(after == expected, 'whole inventory mismatch after packing ' + lane)
            return after, verify_catalogs(verified, catalogs)

        baseline, _ = pack_and_check(packed_base, before, 'baseline-extracted')
        require(sha(packed_base) == SOURCE_ROOTFS_SHA and packed_base.stat().st_size == source.stat().st_size,
                'control repack does not reproduce exact F372')
        trial = Path(spec['trial_binary'])
        target = root/TLS_PATH
        require(not target.is_symlink() and sha(trial) == NEW_TLS_SHA, 'trial target invalid')
        shutil.copyfile(trial, target)
        expected_changes = {TLS_PATH}
        # Preserve all existing catalog entries and formatting, changing only
        # bindings that refer to the one changed binary or changed catalog.
        for _ in range(len(catalogs) + 1):
            updates = 0
            for name in catalogs:
                data = (root/name).read_bytes()
                rows = catalog_rows(data)
                changed = ''.join(sha(root/path.lstrip('/')) + separator + path + '\n'
                                  for _, separator, path in rows).encode('ascii')
                if changed != data:
                    (root/name).write_bytes(changed)
                    expected_changes.add(name)
                    updates += 1
            if not updates:
                break
        else:
            raise ValueError('catalog dependencies failed to converge')
        changed_tree = web.inventory(root)
        require(set(before) == set(changed_tree), 'unexpected topology change')
        actual_changes = {name for name in before if before[name] != changed_tree[name]}
        require(actual_changes == expected_changes, 'unexpected entry change')
        for name in actual_changes:
            require(all(before[name][key] == changed_tree[name][key]
                        for key in ('type', 'mode', 'uid', 'gid')), 'changed metadata: ' + name)
        require(all(before[name] == changed_tree[name] for name in before if name not in actual_changes),
                'unrelated source entry changed')
        after, catalog_checks_after = pack_and_check(packed_new, changed_tree, 'tls-extracted')
        binding_delta = {name: after[name.lstrip('/')]['sha256']
                         for name, digest in spec['runtime_bindings'].items()
                         if after[name.lstrip('/')]['sha256'] != digest}
        write_json(out/'full-inventory-private.json', {'before': before, 'after': after,
                                                     'changed_files': sorted(actual_changes)})
        combined_original = 7782400
        saving = packed_base.stat().st_size - packed_new.stat().st_size
        result = {
            'schema': 'openmitrastar.f372-tls-squashfs-size-experiment/v1',
            'status': 'PASS_CONTROL_REPRODUCED_EXACT_F372_AND_TLS_SIZE_MEASURED',
            'hardware_actions': False, 'flash_artifact_created': False, 'release_eligible': False,
            'source_rootfs': record(source), 'control_rootfs': record(packed_base),
            'tls_substitution_rootfs': record(packed_new), 'squashfs_tool_pins': TOOL_PINS,
            'squashfs_options': options, 'control_reproduces_source_byte_for_byte': True,
            'old_tls_raw_bytes': before[TLS_PATH]['bytes'], 'new_tls_raw_bytes': after[TLS_PATH]['bytes'],
            'raw_tls_saving_bytes': before[TLS_PATH]['bytes'] - after[TLS_PATH]['bytes'],
            'actual_combined_rootfs_saving_bytes': saving, 'rootfs_window_bytes': ROOTFS_WINDOW,
            'old_headroom_bytes': ROOTFS_WINDOW - packed_base.stat().st_size,
            'new_headroom_bytes': ROOTFS_WINDOW - packed_new.stat().st_size,
            'changed_files': sorted(actual_changes), 'unchanged_entries': len(before) - len(actual_changes),
            'catalogs_before': catalog_checks_before, 'catalogs_after': catalog_checks_after,
            'runtime_binding_delta': binding_delta, 'full_delta_verified': True,
            'source_f372_unchanged': True, 'tls_configuration_unchanged': True,
            'https_and_http_not_removed': True,
            'f373_original_rootfs_bytes': combined_original,
            'f373_projected_rootfs_bytes_if_equal_saving': combined_original - saving,
            'f373_projected_overflow_bytes_if_equal_saving': combined_original - saving - ROOTFS_WINDOW,
            'f373_projection_is_not_measured_combined_repack': True,
            'limitations': [
                'Private analysis contains existing device identity and is not a firmware artifact.',
                'The measurement substitutes only the TLS executable plus any existing catalog bindings.',
                'mini_httpd 1.19 remains; wolfSSL 5.9.2 is a newer TLS library, not a new HTTP server.',
                'Existing TLS cipher/configuration is unchanged and is not qualified against this trial.',
                'No physical TLS/CGI/client interoperability, RAM, handshake or startup speed claim.',
                'F373 equal-saving projection is arithmetic, not a measured Doom+TLS co-repack.',
                'No full source rebuild or firmware release qualification is performed.'
            ]
        }
        for path, digest in spec['linux_pins'].items():
            require(sha(path) == digest, 'input drift during repack')
        check_tools()
        write_json(out/'result.json', result)
        print(json.dumps({'status': result['status'], 'actual_combined_rootfs_saving_bytes': saving,
                          'old_rootfs_bytes': packed_base.stat().st_size,
                          'new_rootfs_bytes': packed_new.stat().st_size,
                          'result': str(out/'result.json')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--linux-worker', action='store_true')
    parser.add_argument('--spec', type=Path)
    args = parser.parse_args()
    if args.linux_worker:
        require(args.spec is not None, 'worker spec required')
        worker(args)
        return
    require(os.name == 'nt' and args.spec is None, 'Windows launcher required')
    from init_lyoko_device_host_key import restrict_acl
    device = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
    source = device/'firmware/f372-f371-auc-tqe-observation-device-bound'
    manifest_path = source/'manifest.json'
    require(sha(manifest_path) == SOURCE_MANIFEST_SHA, 'F372 manifest drift')
    manifest = json.loads(manifest_path.read_text())
    rootfs = source/manifest['artifacts']['rootfs_squashfs']['file']
    image = source/manifest['artifacts']['webformat']['file']
    require(sha(rootfs) == SOURCE_ROOTFS_SHA and sha(image) == SOURCE_IMAGE_SHA, 'F372 artifact drift')
    trial_dir = ROOT/'outputs/userland/minihttpd-wolfssl-5.9.2-arc700-cgi-tls-trial'
    trial = trial_dir/'mini_httpd-wolfssl'
    trial_manifest = trial_dir/'manifest.json'
    require(sha(trial) == NEW_TLS_SHA and trial.stat().st_size == 463384, 'TLS trial drift')
    require(json.loads(trial_manifest.read_text())['status'] == 'OFFLINE_LINK_PASS', 'TLS trial not offline qualified')
    script_pins = [Path(__file__), ROOT/'tools/lyoko_web_rootfs_worker.py', ROOT/'tools/f373_rootfs_worker.py',
                   ROOT/'tools/f334_shadow_contract.py', ROOT/'tools/f334_shadow_rootfs_worker.py',
                   manifest_path, source/'rootfs-inventory.json', rootfs, image, trial, trial_manifest]
    pins = {str(path): sha(path) for path in script_pins}
    out = device/'analysis'/('f372-tls-size-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    restrict_acl(out, directory=True)
    spec = {
        'hardware_actions': False, 'source_rootfs': linux(rootfs),
        'source_inventory': linux(source/'rootfs-inventory.json'), 'trial_binary': linux(trial),
        'runtime_bindings': manifest['runtime_bindings'],
        'source_pins': pins, 'linux_pins': {linux(path): digest for path, digest in pins.items()},
        'source_manifest_sha256': SOURCE_MANIFEST_SHA, 'source_image_sha256': SOURCE_IMAGE_SHA,
    }
    spec_path = out/'inputs.json'
    write_json(spec_path, spec)
    print(json.dumps({'started': str(out), 'hardware_actions': False}), flush=True)
    run = subprocess.run(['wsl.exe', '-d', 'REA-Linux', '-u', 'root', '-e', 'python3', linux(Path(__file__)),
                          '--linux-worker', '--spec', linux(spec_path)], capture_output=True, timeout=600)
    (out/'worker.stdout').write_bytes(run.stdout)
    (out/'worker.stderr').write_bytes(run.stderr)
    require(run.returncode == 0, 'TLS repack failed: '+run.stderr.decode(errors='replace')[-1800:])
    require(all(sha(path) == digest for path, digest in pins.items()), 'Windows source changed during repack')
    print(run.stdout.decode(), end='')


if __name__ == '__main__':
    main()
