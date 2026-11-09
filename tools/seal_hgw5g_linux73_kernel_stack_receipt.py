"""Seal a completed fresh kernel/base build and optional native module build."""
import argparse, datetime, hashlib, json, re, shutil
from pathlib import Path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def record(path, root):
    return {'path': str(path.relative_to(root)), 'bytes': path.stat().st_size, 'sha256': sha(path)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--native', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    log = args.kernel / 'build.log'
    text = log.read_text()
    assert not re.search(r'\berror:|^ERROR:|\*\*\*', text, re.M)
    assert (args.kernel / 'vmlinux').stat().st_size > 0
    assert (args.kernel / 'Module.symvers').stat().st_size > 0
    assert 'LD [M]  net/bridge/bridge.ko' in text
    config = (args.kernel / '.config').read_text()
    required = ('CONFIG_OPENMITRASTAR_QDRV_COMPAT=y', 'CONFIG_IPV6=y', 'CONFIG_BRIDGE=m',
                'CONFIG_NET_SCHED=y', 'CONFIG_I2C=y', 'CONFIG_GPIOLIB=y', 'CONFIG_WEXT_CORE=y',
                'CONFIG_WEXT_PRIV=y', 'CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y',
                '# CONFIG_MODULE_FORCE_UNLOAD is not set', '# CONFIG_MODVERSIONS is not set')
    for item in required:
        assert item in config, item
    modules = sorted(args.kernel.rglob('*.ko'))
    shutil.copyfile(log, args.output / 'kernel-build.log')
    shutil.copyfile(args.kernel / '.config', args.output / 'kernel.config')
    shutil.copyfile(args.kernel / 'Module.symvers', args.output / 'kernel.Module.symvers')
    result = {'status': 'PASS_REAL_LINUX73_KERNEL_AND_BASE_MODULES_NATIVE_LINK_PENDING',
              'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'candidate': str(args.candidate), 'candidate_result_sha256': sha(args.candidate / 'result.json'),
              'kernel': str(args.kernel), 'kernel_artifacts': [record(p, args.kernel) for p in
                  [args.kernel / 'vmlinux', args.kernel / '.config', args.kernel / 'Module.symvers'] + modules],
              'base_module_count': len(modules), 'kernel_config_required': list(required),
              'kernel_log_sha256': sha(log), 'hardware_accessed': False, 'firmware_eligible': False}
    if args.native:
        text = (args.native / 'build.log').read_text()
        assert not re.search(r'\berror:|^ERROR:|\*\*\*', text, re.M)
        modules = sorted(args.native.rglob('*.ko'))
        assert len(modules) == 21, len(modules)
        assert 'MODPOST Module.symvers' in text
        assert (args.native / 'Module.symvers').stat().st_size > 0
        shutil.copyfile(args.native / 'build.log', args.output / 'native-build.log')
        shutil.copyfile(args.native / 'Module.symvers', args.output / 'native.Module.symvers')
        result.update(status='PASS_REAL_LINUX73_KERNEL_BASE_AND_21_NATIVE_MODULES_OFFLINE',
                      native=str(args.native), native_module_count=len(modules),
                      native_modules=[record(p, args.native) for p in modules],
                      native_log_sha256=sha(args.native / 'build.log'))
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'base_module_count': result['base_module_count'],
                      'result_sha256': sha(args.output / 'result.json')}, indent=2))

if __name__ == '__main__':
    main()
