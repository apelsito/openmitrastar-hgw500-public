"""Offline source/config-pinned kernel and native stack build in new outputs.

Run inside the existing Linux build environment; all caller paths are explicit.
This never installs modules, boots an image, opens a UART or contacts a router.
"""
import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log):
    with log.open('wb') as output:
        return subprocess.run(command, stdout=output, stderr=subprocess.STDOUT).returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--kernel-source', type=Path, required=True)
    parser.add_argument('--kernel-config', type=Path, required=True)
    parser.add_argument('--gpl-source', type=Path, required=True)
    parser.add_argument('--cross-prefix', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    assert args.jobs > 0
    candidate = args.candidate.resolve()
    kernel_source = args.kernel_source.resolve()
    config = args.kernel_config.resolve()
    gpl = args.gpl_source.resolve()
    out = args.output.resolve()
    proof = json.loads((candidate / 'result.json').read_text())
    for stored_rel, expected in proof['files'].items():
        rel = stored_rel.replace('\\', '/')
        assert sha(candidate / rel) == expected, rel
    assert sha(candidate / 'Kbuild') == proof['kbuild_sha256']
    for stored_rel in proof['files']:
        rel = stored_rel.replace('\\', '/')
        if rel.startswith('kernel-overlay/'):
            src = candidate / rel
            target = kernel_source / rel[len('kernel-overlay/'):]
            assert target.is_file() and sha(src) == sha(target), str(target)
    gcc = Path(args.cross_prefix + 'gcc').resolve()
    assert gcc.is_file()
    out.mkdir(parents=True, exist_ok=False)
    kernel = out / 'kernel'
    modules = out / 'native-stack'
    kernel.mkdir()
    modules.mkdir()
    configuration = re.sub(r'(?m)^CONFIG_INITRAMFS_SOURCE=.*\n',
                           'CONFIG_INITRAMFS_SOURCE=""\n', config.read_text())
    (kernel / '.config').write_text(configuration)
    for group in ('source', 'headers', 'providers'):
        shutil.copytree(candidate / group, modules / group)
    shutil.copyfile(candidate / 'Kbuild', modules / 'Kbuild')
    build = ['make', '-C', str(kernel_source), 'O=' + str(kernel),
             'ARCH=arc', 'CROSS_COMPILE=' + args.cross_prefix]
    result = {'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'candidate': str(candidate), 'candidate_result_sha256': sha(candidate / 'result.json'),
              'input_config_sha256': sha(config), 'gcc_sha256': sha(gcc),
              'kernel_source': str(kernel_source), 'output': str(out),
              'hardware_accessed': False, 'firmware_eligible': False,
              'private_initramfs_excluded': True, 'dtbs_built': False, 'phases': []}
    commands = [('configure', build + ['olddefconfig']),
                ('kernel_and_base_modules', build + ['-j' + str(args.jobs), 'vmlinux', 'modules']),
                ('native_modules', build + ['M=' + str(modules), 'QTN_GPL=' + str(gpl),
                                           '-j' + str(args.jobs), 'modules'])]
    for name, command in commands:
        log = out / (name + '.log')
        rc = run(command, log)
        result['phases'].append({'phase': name, 'argv': command, 'exit_code': rc, 'log_sha256': sha(log)})
        if rc:
            result['status'] = 'STOP_' + name.upper()
            break
    else:
        result['status'] = 'PASS_KERNEL_BASE_AND_NATIVE_MODULES_OFFLINE'
        result['artifacts'] = {str(p.relative_to(out)): {'bytes': p.stat().st_size, 'sha256': sha(p)}
                               for p in [kernel / 'vmlinux', kernel / '.config', kernel / 'Module.symvers']
                               + sorted(kernel.rglob('*.ko')) + sorted(modules.rglob('*.ko'))}
    result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'result': str(out / 'result.json')}, indent=2))
    raise SystemExit(0 if result['status'].startswith('PASS_') else 1)


if __name__ == '__main__':
    main()
