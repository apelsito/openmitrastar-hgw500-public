"""Two clean offline builds of current kernel/base/QTN/EMAC, with common ABI pins."""
import argparse, datetime, hashlib, json, os, re, shutil, subprocess
from pathlib import Path

EPOCH = '1792365298'
GCC = '3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def execute(command, log, env):
    with log.open('xb') as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, env=env, check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','kernel-source','kernel-config','gpl-source','emac-builder','output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--cross-prefix', required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    source = args.kernel_source.resolve(); candidate = args.candidate.resolve()
    output = args.output.resolve(); config = args.kernel_config.resolve()
    gpl = args.gpl_source.resolve(); emac = args.emac_builder.resolve()
    assert not output.exists(), 'Use new output'
    assert 1 <= args.jobs <= 32
    proof = json.loads((candidate / 'result.json').read_text())
    for stored_rel, expected in proof['files'].items():
        rel = stored_rel.replace('\\', '/')
        assert sha(candidate / rel) == expected, rel
        if rel.startswith('kernel-overlay/'):
            assert sha(source / rel[len('kernel-overlay/'):]) == expected, rel
    assert sha(candidate / 'Kbuild') == proof['kbuild_sha256']
    compiler = Path(args.cross_prefix + 'gcc')
    assert sha(compiler) == GCC
    cfg = config.read_text()
    cfg = re.sub(r'(?m)^CONFIG_INITRAMFS_SOURCE=.*\n', 'CONFIG_INITRAMFS_SOURCE=""\n', cfg)
    assert 'CONFIG_QTN_TOPAZ_ETH73=y' in cfg and 'CONFIG_OPENMITRASTAR_QDRV_COMPAT=y' in cfg
    output.mkdir(parents=True)
    result = {'schema': 'openmitrastar.linux73-native-pair/v1', 'status': 'RUNNING',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'candidate': str(candidate), 'candidate_result_sha256': sha(candidate / 'result.json'),
              'kernel_source': str(source), 'input_config_sha256': sha(config),
              'gcc_sha256': GCC, 'initramfs_excluded': True, 'dtbs_built': False,
              'old_objects_reused': False, 'hardware_accessed': False, 'firmware_eligible': False,
              'lanes': []}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    try:
        for name in ('a','b'):
            lane = output / name; lane.mkdir()
            kernel = lane / 'kernel'; kernel.mkdir(); (kernel / '.config').write_text(cfg)
            native = lane / 'native'; native.mkdir()
            for group in ('source','headers','providers'):
                shutil.copytree(candidate / group, native / group)
            shutil.copyfile(candidate / 'Kbuild', native / 'Kbuild')
            flags = '-ffile-prefix-map=' + str(lane) + '=/hgw73-pair -fmacro-prefix-map=' + str(lane) + '=/hgw73-pair'
            env = os.environ | {'SOURCE_DATE_EPOCH': EPOCH, 'KBUILD_BUILD_TIMESTAMP': '@' + EPOCH,
                'KBUILD_BUILD_USER': 'openmitrastar', 'KBUILD_BUILD_HOST': 'aelita73',
                'KBUILD_BUILD_VERSION': '1', 'KCFLAGS': flags}
            make = ['make','-C',str(source),'O=' + str(kernel),'ARCH=arc','CROSS_COMPILE=' + args.cross_prefix]
            execute(make + ['olddefconfig'], lane / 'configure.log', env)
            execute(make + ['-j' + str(args.jobs),'vmlinux','modules'], lane / 'kernel.log', env)
            execute(make + ['M=' + str(native),'QTN_GPL=' + str(gpl),'-j' + str(args.jobs),'modules'], lane / 'native.log', env)
            symvers_sha = sha(kernel / 'Module.symvers'); config_sha = sha(kernel / '.config')
            execute(['python3',str(emac),'--kernel-source',str(source),'--kernel-context',str(kernel),
                     '--output',str(lane / 'emac'),'--toolchain-prefix',args.cross_prefix,
                     '--expected-config-sha256',config_sha,'--expected-symvers-sha256',symvers_sha,
                     '--jobs',str(args.jobs),'--build'], lane / 'emac.log', env)
            artifacts = [kernel / 'vmlinux',kernel / '.config',kernel / 'Module.symvers']
            artifacts += sorted(kernel.rglob('*.ko')) + sorted(native.rglob('*.ko'))
            artifacts += sorted((lane / 'emac').rglob('*.ko'))
            native_units = sorted((native / 'source').rglob('*.o')) + sorted((native / 'providers').rglob('*.o'))
            assert len(native_units) == 72
            assert len(list(native.rglob('*.ko'))) == 21
            lane_result = {'name':name,'C_units':len(native_units),'kernel_config_sha256':config_sha,
                'kernel_symvers_sha256':symvers_sha,'base_module_count':len(list(kernel.rglob('*.ko'))),
                'native_module_count':21,'emac_module_count':1,
                'artifacts':{p.relative_to(lane).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in artifacts},
                'C_objects':{p.relative_to(native).as_posix():sha(p) for p in native_units}}
            result['lanes'].append(lane_result)
            (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            print('PASS fresh lane ' + name, flush=True)
        left,right = result['lanes']
        assert left['artifacts'].keys() == right['artifacts'].keys()
        mismatches = [path for path in left['artifacts'] if left['artifacts'][path] != right['artifacts'][path]]
        object_mismatches = [path for path in left['C_objects'] if left['C_objects'][path] != right['C_objects'][path]]
        result.update(status='PASS_PAIRED_KERNEL_BASE_21_NATIVE_EMAC_BYTES' if not mismatches and not object_mismatches
                       else 'NO_GO_PAIRED_ARTIFACT_REPRODUCIBILITY', artifact_mismatches=mismatches,
                      C_object_mismatches=object_mismatches)
    except Exception as error:
        result.update(status='STOP_PAIRED_BUILD',error=str(error))
        raise
    finally:
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'status':result['status'],'output':str(output)}, indent=2), flush=True)
    raise SystemExit(0 if result['status'].startswith('PASS_') else 1)

if __name__ == '__main__':
    main()
