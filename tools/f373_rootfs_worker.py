"""Offline F373 complete Doom/LED/timing repack; never creates a flash image."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog, parse_artifact_catalog

VERSION = 'lyoko-foundation-6.13.0-f373-doom-english-led-timing-device'
RELEASE = 'etc/openmitrastar/release'
LED = 'usr/sbin/om-ledctl'
RCS = 'etc/init.d/rcS'
DOOM_CATALOG = 'usr/share/openmitrastar/doom/artifacts.sha256'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_catalogs(root, names):
    checks = {}
    for name in names:
        rows = catalog_rows((root/name).read_bytes())
        for digest, _, path in rows:
            relative = path.lstrip('/')
            assert sha((root/relative).read_bytes()) == digest, 'catalog hash mismatch '+name+' '+relative
        checks[name] = len(rows)
    return checks


def catalog_rows(data):
    assert data.endswith(b'\n') and b'\r' not in data and len(data) <= 262144
    rows = []
    seen = set()
    for line in data.decode('ascii').splitlines():
        # F372 radio2g uses one separator space; preserve its exact formatting.
        match = re.fullmatch(r'([0-9a-f]{64})( {1,2})(/[A-Za-z0-9_./+-]+)', line)
        assert match, 'invalid inherited catalog row'
        path = match[3]
        assert '..' not in PurePosixPath(path).parts and path not in seen
        seen.add(path)
        rows.append((match[1], match[2], path))
    assert rows
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'input_manifest', 'image', 'result'):
        p.add_argument('--'+key.replace('_', '-'), type=Path, required=True)
    p.add_argument('--source-sha', required=True)
    p.add_argument('--input-manifest-sha', required=True)
    p.add_argument('--build-id', required=True)
    p.add_argument('--epoch', type=int, required=True)
    a = p.parse_args()
    assert os.name == 'posix' and os.geteuid() == 0
    assert not a.image.exists() and not a.result.exists()
    assert sha(a.source.read_bytes()) == a.source_sha
    assert sha(a.input_manifest.read_bytes()) == a.input_manifest_sha
    inputs = json.loads(a.input_manifest.read_text())
    assert inputs['version'] == VERSION and inputs['hardware_actions'] is False
    content = {}
    for row in inputs['files']:
        name = row['destination']
        assert PurePosixPath(name).as_posix() == name and not PurePosixPath(name).is_absolute()
        assert '..' not in PurePosixPath(name).parts
        assert name.startswith('www/Doom/') or name in (LED, RCS)
        path = Path(row['linux_path'])
        data = path.read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
        assert name not in content
        content[name] = (data, row['mode'])
    assert LED in content and RCS in content and 'www/Doom/index.html' in content
    index = content['www/Doom/index.html'][0]
    assert b'lang="en"' in index and b'doom19s.zip' in index and b'freedoom' not in index.lower()
    with tempfile.TemporaryDirectory(prefix='f373-rootfs-', dir='/tmp') as directory:
        root = Path(directory)/'root'
        verified = Path(directory)/'verified'
        packed = Path(directory)/'rootfs.squashfs'
        subprocess.run(['unsquashfs', '-processors', '1', '-no-progress', '-d', str(root), str(a.source)],
                       check=True, stdout=subprocess.DEVNULL)
        before = web.inventory(root)
        assert before[LED]['sha256'] == inputs['expected_parent_led_sha256']
        assert before[RCS]['sha256'] == inputs['expected_parent_rcs_sha256']
        assert not any(name.startswith('www/Doom') for name in before)
        verify_artifact_catalog(root)
        catalogs = sorted(name for name, row in before.items()
                          if row['type'] == 'file' and name.startswith('usr/share/openmitrastar/')
                          and name.endswith('/artifacts.sha256'))
        before_catalogs = verify_catalogs(root, catalogs)
        release = (root/RELEASE).read_text().splitlines()
        assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.12.3-f372-auc-tqe-observation-device' in release
        content[RELEASE] = (('\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if line.startswith('OPENMITRASTAR_PRODUCT_VERSION=')
                                       else 'OPENMITRASTAR_BUILD_ID='+a.build_id if line.startswith('OPENMITRASTAR_BUILD_ID=')
                                       else line for line in release)+'\n').encode(), before[RELEASE]['mode'])
        game_names = sorted(name for name in content if name.startswith('www/Doom/'))
        content[DOOM_CATALOG] = ((''.join(sha(content[name][0])+'  /'+name+'\n' for name in game_names)).encode(), 0o644)
        # Update every existing artifact catalogue for changed bytes, preserving
        # all path entries. Resolve catalog-to-catalog bindings to a fixed point.
        for _ in range(len(catalogs)+1):
            updates = 0
            for name in catalogs:
                original = (root/name).read_bytes()
                rows = []
                for digest, separator, path in catalog_rows(original):
                    relative = path.lstrip('/')
                    rows.append((sha(content[relative][0]) if relative in content else digest)+separator+path)
                changed = ('\n'.join(rows)+'\n').encode()
                if changed != original and content.get(name, (None,))[0] != changed:
                    content[name] = (changed, before[name]['mode'])
                    updates += 1
            if not updates:
                break
        else:
            raise ValueError('catalog dependency did not converge')
        expected = {name: put(root, name, data, mode) for name, (data, mode) in content.items()}
        # put() preserves modes for files; newly introduced directory metadata
        # must be deterministic despite a caller's umask.
        for name in web.inventory(root).keys()-before.keys():
            path = root/name
            if path.is_dir():
                path.chmod(0o755)
                os.chown(path, 0, 0)
        web.validate_delta(before, web.inventory(root), expected)
        verify_artifact_catalog(root)
        complete_catalogs = catalogs+[DOOM_CATALOG]
        verify_catalogs(root, complete_catalogs)
        for name in (LED, RCS):
            subprocess.run(['sh', '-n', str(root/name)], check=True)
        subprocess.run(['mksquashfs', str(root), str(packed), '-noappend', '-all-root', '-comp', 'xz',
                        '-b', '131072', '-no-xattrs', '-no-exports', '-all-time', str(a.epoch),
                        '-mkfs-time', str(a.epoch), '-processors', '1', '-no-progress'],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['unsquashfs', '-processors', '1', '-no-progress', '-d', str(verified), str(packed)],
                       check=True, stdout=subprocess.DEVNULL)
        after = web.inventory(verified)
        checks = web.validate_delta(before, after, expected)
        verify_artifact_catalog(verified)
        catalog_checks = verify_catalogs(verified, complete_catalogs)
        assert all(before[name] == after[name] for name in before if name not in content)
        shutil.copyfile(packed, a.image)
        report = dict(schema='openmitrastar.f373-analysis-rootfs/v1',
                      status='PACKED_VERIFIED_ANALYSIS_ROOTFS_ONLY', version=VERSION,
                      before=before, after=after, checks=checks, changed_files=sorted(content),
                      catalogs_before=before_catalogs, catalogs_after=catalog_checks,
                      all_other_entries_unchanged=True, image_sha256=sha(packed.read_bytes()),
                      image_bytes=packed.stat().st_size, complete_game_files=game_names,
                      kernel_driver_calibration_regulatory_identity_unchanged=True,
                      hardware_actions=False, flash_artifact_created=False)
        a.result.write_text(json.dumps(report, sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
