"""Fix only the F363 startup admission of its S16-owned temperature module."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put

VERSION = 'lyoko-foundation-6.9.11-f363r2-temperature-owner-device'
START = 'usr/sbin/om-radio5-start'
CATALOGS = ('usr/share/openmitrastar/radio5g/artifacts.sha256',
            'usr/share/openmitrastar/storage/artifacts.sha256',
            'usr/share/openmitrastar/temperature/artifacts.sha256')
OLD_START_SHA = '59e84ce1ffd76ffdb88389336fc494502b9a5162241378b311b484c4b7882ba4'
OLD_GATE = 'for dirty in qdrv wlan temp_sensor temp_sens switch_emac switch_tqe hbm fwt_ctrl; do\n\t! grep -Eq "^${dirty} " /proc/modules || { unset psk mac; refuse "dirty-$dirty"; }\ndone\n'
REQUIRE = '/usr/sbin/om-temperature-f363 require-module || refuse f363-preloaded-temperature-module\n'
NEW_GATE = ('# S16 owns the F363 hwmon provider before radio startup. Admit only its\n'
            '# named/versioned node; these checks read registration metadata, not MMIO.\n'
            '[ -d /sys/module/hwmon ] && [ -d /sys/module/temp_sens ] || refuse f363-preloaded-temperature-module\n'
            + REQUIRE + OLD_GATE.replace('temp_sensor temp_sens ', 'temp_sensor '))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_start(data):
    assert sha(data) == OLD_START_SHA
    text = data.decode('utf-8')
    assert text.count(OLD_GATE) == 1
    # Keep the existing require-module at the former load position as well;
    # only startup admission changes, not the dependency sequence.
    assert text.count('/usr/sbin/om-temperature-f363 require-module || refuse f363-temperature-module') == 1
    return text.replace(OLD_GATE, NEW_GATE).encode('utf-8')


def catalogs(root):
    rows = []
    for catalog in CATALOGS:
        for line in (root/catalog).read_text().splitlines():
            digest, path = line.split('  ', 1)
            body = (root/path.lstrip('/')).read_bytes()
            actual = sha(body)
            assert actual == digest, path
            rows.append(dict(catalog=catalog, path=path, bytes=len(body), sha256=actual))
    return rows


def test_admission(root, old, new, scratch):
    """Run only the real admission fragment with fake /sys and /proc files."""
    helper = (root/'usr/sbin/om-temperature-f363').read_text()
    start = helper.index('find_sensor()\n{')
    end = helper.index('\nstatus()\n', start)
    finder = helper[start:end].replace('/sys/', '"$FIXTURE"/sys/')
    outcomes = []
    cases = (('old-rejects-legitimate-S16', OLD_GATE, '363', 'temp_sens', True, 23, 'dirty-temp_sens'),
             ('new-admits-legitimate-S16', NEW_GATE, '363', 'temp_sens', True, 0, 'ADMITTED'),
             ('new-rejects-foreign-profile', NEW_GATE, '339', 'temp_sens', True, 23, 'f363-preloaded-temperature-module'),
             ('new-rejects-missing-hwmon', NEW_GATE, '363', 'temp_sens', False, 23, 'f363-preloaded-temperature-module'),
             ('new-still-rejects-qdrv', NEW_GATE, '363', 'temp_sens\nqdrv', True, 23, 'dirty-qdrv'),
             ('new-still-rejects-legacy-temp', NEW_GATE, '363', 'temp_sens\ntemp_sensor', True, 23, 'dirty-temp_sensor'))
    assert OLD_GATE in old.decode() and NEW_GATE in new.decode()
    for name, fragment, version, modules, hwmon, expected_rc, expected_line in cases:
        fixture = scratch/name
        (fixture/'sys/module/temp_sens').mkdir(parents=True)
        if hwmon:
            (fixture/'sys/module/hwmon').mkdir()
        (fixture/'sys/module/temp_sens/version').write_text(version+'\n')
        (fixture/'sys/class/hwmon/hwmon0').mkdir(parents=True)
        (fixture/'sys/class/hwmon/hwmon0/name').write_text('topaz_internal\n')
        (fixture/'modules').write_text(''.join(n+' 123 0 - Live 0\n' for n in modules.splitlines()))
        code = ('set -eu\nrefuse() { printf "%s\\n" "$1"; exit 23; }\n'+finder+'\n'
                + fragment.replace('/proc/modules', '"$FIXTURE"/modules')
                  .replace('/sys/', '"$FIXTURE"/sys/')
                  .replace('/usr/sbin/om-temperature-f363 require-module', 'find_sensor')
                + 'printf "ADMITTED\\n"\n')
        script = fixture/'gate.sh'
        script.write_text(code)
        run = subprocess.run(['sh', str(script)], env={**os.environ, 'FIXTURE': str(fixture)},
                             capture_output=True, timeout=5)
        assert run.returncode == expected_rc and run.stdout.decode().strip() == expected_line and not run.stderr, name
        outcomes.append(dict(case=name, exit_code=run.returncode, result=run.stdout.decode().strip()))
    return dict(status='PASS_EXTRACTED_ADMISSION_FAKE_SYSFS_PROC', cases=outcomes,
                hardware_actions=False, whole_radio_helper_executed=False,
                actual_find_sensor_function_sha256=sha(helper[start:end].encode()))


def main():
    ap = argparse.ArgumentParser()
    for name in ('source', 'image', 'result'):
        ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--source-sha', required=True)
    ap.add_argument('--build-id', required=True)
    ap.add_argument('--epoch', required=True, type=int)
    args = ap.parse_args()
    assert os.name == 'posix' and os.geteuid() == 0
    assert not args.image.exists() and not args.result.exists()
    assert sha(args.source.read_bytes()) == args.source_sha
    with tempfile.TemporaryDirectory(prefix='f363r2-rootfs-', dir='/tmp') as directory:
        scratch = Path(directory); root = scratch/'root'; verified = scratch/'verified'
        subprocess.run(['unsquashfs', '-processors', '1', '-no-progress', '-d', str(root), str(args.source)],
                       check=True, stdout=subprocess.DEVNULL)
        before = web.inventory(root)
        original_catalogs = catalogs(root)
        old = (root/START).read_bytes(); new = patch_start(old)
        tests = test_admission(root, old, new, scratch)
        release = (root/'etc/openmitrastar/release').read_text().splitlines()
        release = '\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if line.startswith('OPENMITRASTAR_PRODUCT_VERSION=')
                            else 'OPENMITRASTAR_BUILD_ID='+args.build_id if line.startswith('OPENMITRASTAR_BUILD_ID=')
                            else line for line in release)+'\n'
        changes = {START: (new, 0o755), 'etc/openmitrastar/release': (release.encode(), 0o644)}
        for catalog in CATALOGS:
            old_catalog = (root/catalog).read_bytes(); lines = []
            for line in old_catalog.decode().splitlines():
                digest, path = line.split('  ', 1); name = path.lstrip('/')
                lines.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
            body = ('\n'.join(lines)+'\n').encode()
            if body != old_catalog:
                changes[catalog] = (body, 0o644)
        expected = {name: put(root, name, body, mode) for name, (body, mode) in changes.items()}
        assert set(changes) == {START, 'etc/openmitrastar/release', CATALOGS[0], CATALOGS[1]}
        web.validate_delta(before, web.inventory(root), expected)
        subprocess.run(['sh', '-n', str(root/START)], check=True)
        subprocess.run(['mksquashfs', str(root), str(args.image), '-noappend', '-all-root', '-comp', 'xz',
                        '-b', '131072', '-no-xattrs', '-no-exports', '-all-time', str(args.epoch),
                        '-mkfs-time', str(args.epoch), '-processors', '1', '-no-progress'],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['unsquashfs', '-processors', '1', '-no-progress', '-d', str(verified), str(args.image)],
                       check=True, stdout=subprocess.DEVNULL)
        after = web.inventory(verified); checks = web.validate_delta(before, after, expected)
        final_catalogs = catalogs(verified)
        for name in before:
            if name not in changes:
                assert before[name] == after[name], name
        args.result.write_text(json.dumps(dict(status='PASS_F363R2_ROOTFS_ADMISSION_FIX', before=before,
            after=after, changed_files=sorted(changes), checks=checks, tests=tests,
            catalogs_before=original_catalogs, catalogs_after=final_catalogs,
            all_kernel_modules_unchanged=True, hardware_actions=False), sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
