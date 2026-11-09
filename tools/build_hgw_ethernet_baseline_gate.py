"""Rebuild unchanged F352 twice using its retained ARC commands, offline.

Run on REA-Linux. Only a new timestamped output directory is written. The
historical F340 kernel tree is absent: retained F363 generated headers and the
recovered Linux 5.10.260 header tree are checked against the complete baseline.
No package, firmware, device, network, UART, or installation action is present.
"""
import argparse
from datetime import datetime, timezone
import glob
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path('/workspace/user-home/Desktop/MitraStar')
KERNEL = Path('/home/rea/openmitrastar-f368-build-20261021/linux-5.10.260')
CONTEXT = Path('/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z/kernel')
OLD_KERNEL = '/home/user/openmitrastar-build/f340-watchdog-20260921T132951Z/linux'
PARENT = ROOT/'outputs/kernel-port/f352-dual-emac-20260921T162320Z/a'
SOURCE = ROOT/'work/kernel-port/modules/f352_dual_emac'
NAME = 'qtn-topaz-emac-f352'
EXPECTED = '41c5cb625b22776d0075207760df59fd20d4a34bddb1c7568adfa83391cbc05e'
EXPECTED_SOURCE = '011e42eb8fda62686b9b55dd210f1104540c5c3ec65f20d7f4035812e55e64f2'
EXPECTED_CONFIG = 'ee4c4d98622b2c5caf94bebd4e4e3afa7888f1eb4630b4e86958dbbffdb7a61a'
TC = ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def run(command, cwd, log):
    save(log.with_suffix('.command.json'), command)
    proc = subprocess.run(command, cwd=cwd, capture_output=True)
    log.with_suffix('.stdout').write_bytes(proc.stdout)
    log.with_suffix('.stderr').write_bytes(proc.stderr)
    if proc.returncode:
        raise RuntimeError(str(log)+': '+proc.stderr.decode(errors='replace')[-2800:])
    return proc.stdout


def resolve_dependency(value):
    value = value.replace(OLD_KERNEL, str(KERNEL))
    if value.startswith(str(PARENT)):
        value = value.replace(str(PARENT), str(SOURCE), 1)
    path = Path(value)
    return path if path.is_absolute() else CONTEXT/path


def retained_dependencies(template):
    """Pin all historical includes before compilation, including wildcards."""
    data = template.read_text()
    body = data.split('\ndeps_', 1)[1].split(' := ', 1)[1].split('\n\n', 1)[0]
    found = set()
    missing = []
    for line in body.splitlines():
        value = line.strip().removesuffix('\\').strip()
        if not value:
            continue
        if value.startswith('$(wildcard ') and value.endswith(')'):
            pattern = value[len('$(wildcard '):-1]
            found.update(Path(p) for p in glob.glob(str(resolve_dependency(pattern))))
        else:
            path = resolve_dependency(value)
            if path.is_file():
                found.add(path)
            else:
                missing.append(str(path))
    return found, missing


def command(folder, metadata=False):
    stem = NAME+'.mod' if metadata else NAME
    template = PARENT/('.'+stem+'.o.cmd')
    args = shlex.split(template.read_text().splitlines()[0].split(' := ', 1)[1])
    result = []
    relative = {'-I./arch/arc/include/generated', '-I./include',
                '-I./arch/arc/include/generated/uapi', '-I./include/generated/uapi'}
    for arg in args:
        arg = arg.replace(OLD_KERNEL, str(KERNEL)).replace(str(PARENT), str(folder))
        if arg.startswith('-Wp,-MMD,'):
            arg = '-Wp,-MMD,'+str(folder/(stem+'.d'))
        if arg in relative:
            arg = '-I'+str(CONTEXT/arg[4:])
        result.append(arg)
    result[result.index('-o')+1] = str(folder/(stem+'.o'))
    result[-1] = str(folder/(stem+'.c'))
    # Explicitly restore only relocated source path literals. No code/data
    # bytes or ELF fields are patched after compilation.
    result[result.index('-c'):result.index('-c')] = [
        '-fmacro-prefix-map='+str(folder)+'='+str(PARENT),
        '-ffile-prefix-map='+str(folder)+'='+str(PARENT),
        '-fmacro-prefix-map='+str(KERNEL)+'/=',
    ]
    return result


def actual_dependencies(path):
    value = path.read_text().split(':', 1)[1].replace('\\\n', ' ')
    return {Path(p).resolve() for p in shlex.split(value) if Path(p).is_file()}


def elf_modinfo(elf):
    found = {}
    for value in elf.byname['.modinfo']['data'].split(b'\0'):
        if b'=' in value:
            key, entry = value.decode(errors='replace').split('=', 1)
            found.setdefault(key, []).append(entry)
    return {key: sorted(value) for key, value in found.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = args.output or ROOT/'outputs/rea'/('ethernet-baseline-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'openmitrastar.hgw-ethernet-baseline/v1',
              'status': 'NO_GO_BASELINE_BUILD', 'hardware_accessed': False,
              'firmware_created': False, 'installed': False, 'physical_gates': 'UNRUN'}
    try:
        # Existing ELF comparison covers every section, symbol, and RELA.
        sys.path.insert(0, str(ROOT/'tools'))
        import qualify_f370_qdrv_module as comparison
        parent_module = PARENT/(NAME+'.ko')
        assert sha(parent_module) == EXPECTED and parent_module.stat().st_size == 24544
        assert sha(SOURCE/(NAME+'.c')) == EXPECTED_SOURCE, 'F352 source drift'
        assert sha(CONTEXT/'.config') == EXPECTED_CONFIG, 'generated config drift'
        assert sha(KERNEL/'include/linux/soc/qtn/topaz-ethernet.h') == sha(ROOT/'work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h')
        protected = {Path(__file__).resolve(), ROOT/'tools/qualify_f370_qdrv_module.py',
                     ROOT/'tools/build_f370_qdrv_module.py', ROOT/'tools/compile_f368_changed_objects.py',
                     CONTEXT/'.config', CONTEXT/'Module.symvers', CONTEXT/'include/generated/autoconf.h',
                     CONTEXT/'scripts/mod/modpost',
                     CONTEXT/'scripts/module.lds', parent_module, PARENT/(NAME+'.o'),
                     PARENT/(NAME+'.mod.o'), KERNEL.parent/'linux-5.10.260.tar.xz',
                     Path(str(TC)+'gcc').resolve(), Path(str(TC)+'ld').resolve()}
        protected.update(p for p in SOURCE.iterdir() if p.is_file())
        missing = []
        for stem in (NAME, NAME+'.mod'):
            template = PARENT/('.'+stem+'.o.cmd')
            protected.add(template)
            includes, absent = retained_dependencies(template)
            protected.update(includes)
            missing.extend(absent)
        save(out/'missing-retained-dependencies.json', missing)
        assert not missing, 'retained header dependencies missing'
        pins = {str(p): sha(p) for p in sorted(protected)}
        save(out/'input-pins.json', pins)
        parent_elf = comparison.Elf(parent_module)
        objects = []
        for lane in ('a', 'b'):
            folder = out/lane
            folder.mkdir()
            for name in (NAME+'.c', 'f352_contract.h', 'f352_pair.inc'):
                (folder/name).write_bytes((SOURCE/name).read_bytes())
            run(command(folder), CONTEXT, folder/'compile-driver')
            deps = actual_dependencies(folder/(NAME+'.d'))
            actual_pins = {str(p): sha(p) for p in sorted(deps)}
            save(folder/'actual-header-pins.json', actual_pins)
            unpinned = {p for p in deps if str(p) not in pins and not p.is_relative_to(folder)}
            assert not unpinned, 'compiler used headers absent from precompile pins: '+str(unpinned)
            # Recreate the dependency metadata consumed by modpost; the original
            # source command has been retained separately in input-pins.json.
            obj = folder/(NAME+'.o')
            (folder/('.'+NAME+'.o.cmd')).write_text(
                'source_'+str(obj)+' := '+str(folder/(NAME+'.c'))+'\n\n'
                +'deps_'+str(obj)+' := \\\n'+''.join('  '+str(p)+' \\\n' for p in sorted(deps))+'\n')
            (folder/(NAME+'.mod')).write_text(str(obj)+'\n')
            run([str(CONTEXT/'scripts/mod/modpost'), '-E', '-e', '-i', str(CONTEXT/'Module.symvers'),
                 '-o', str(folder/'Module.symvers'), str(obj)], folder, folder/'modpost')
            run(command(folder, True), CONTEXT, folder/'compile-metadata')
            metadata_deps = actual_dependencies(folder/(NAME+'.mod.d'))
            assert all(str(p) in pins or p.is_relative_to(folder) for p in metadata_deps), 'unpinned metadata header'
            save(folder/'actual-metadata-header-pins.json', {str(p): sha(p) for p in sorted(metadata_deps)})
            run([str(TC)+'ld', '-r', '-z', 'noexecstack', '--no-warn-rwx-segments', '--build-id=sha1',
                 '-T', str(CONTEXT/'scripts/module.lds'), '-o', str(folder/(NAME+'.ko')),
                 str(obj), str(folder/(NAME+'.mod.o'))], CONTEXT, folder/'link-module')
            module = folder/(NAME+'.ko')
            rebuilt = comparison.Elf(module)
            full = comparison.baseline_compare(parent_elf, rebuilt)
            object_compare = comparison.baseline_compare(comparison.Elf(PARENT/(NAME+'.o')), comparison.Elf(obj))
            save(folder/'full-module-comparison.json', full)
            save(folder/'full-object-comparison.json', object_compare)
            metadata = {'parent': elf_modinfo(parent_elf), 'rebuilt': elf_modinfo(rebuilt)}
            save(folder/'modinfo-comparison.json', metadata)
            metadata_match = metadata['parent'] == metadata['rebuilt']
            imports = sorted(s['name'] for s in rebuilt.syms if s['section'] == 0 and s['name'])
            old_imports = sorted(s['name'] for s in parent_elf.syms if s['section'] == 0 and s['name'])
            save(folder/'imports.json', {'parent': old_imports, 'rebuilt': imports, 'equal': imports == old_imports})
            assert full['status'] == 'PASS_FULL_BASELINE_RECONSTRUCTION', full['errors']
            assert object_compare['status'] == 'PASS_FULL_BASELINE_RECONSTRUCTION', object_compare['errors']
            assert metadata_match and imports == old_imports, 'metadata/import delta'
            assert not (folder/'Module.symvers').read_text().strip(), 'unexpected module exports'
            for p, h in {**actual_pins, **pins}.items():
                assert sha(p) == h, 'input changed during build '+p
            objects.append({'lane': lane, 'path': str(module), 'sha256': sha(module), 'bytes': module.stat().st_size,
                            'whole_file_exact': sha(module) == EXPECTED, 'functions': full['function_count'],
                            'relocations': full['relocations_total'], 'symbols': full['symbols_total'],
                            'imports': len(imports), 'full_object_comparison': object_compare['status']})
            print(json.dumps(objects[-1]), flush=True)
        assert objects[0]['sha256'] == objects[1]['sha256'], 'double build mismatch'
        result.update(status='PASS_OFFLINE_COMPLETE_ETHERNET_BASELINE', modules=objects,
                      parent_sha256=EXPECTED, whole_file_exact=all(r['whole_file_exact'] for r in objects),
                      reproducible=True, inputs_unchanged=True, precompile_pinned_files=len(pins),
                      kernel_source=str(KERNEL), generated_context=str(CONTEXT),
                      limits=['Complete unchanged F352 ET_REL comparison before runtime relocations.',
                              'Missing historical F358 full kernel tree is not reconstructed by this gate.',
                              'No hardware stop/reset, traffic, cold boot, install or release acceptance.'])
    except Exception as error:
        result['error'] = str(error)
    save(out/'result.json', result)
    print(json.dumps({'result': str(out/'result.json'), **result}), flush=True)
    return int(result['status'] != 'PASS_OFFLINE_COMPLETE_ETHERNET_BASELINE')


if __name__ == '__main__':
    raise SystemExit(main())
