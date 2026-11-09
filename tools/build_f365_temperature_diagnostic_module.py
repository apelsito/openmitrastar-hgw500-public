"""Build only the instrumented temperature module against isolated F363 context."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'work/kernel-port/versions/f365-temperature-data-diagnostic'
COMPONENTS = Path('/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/result.json')
F364 = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f364r3-fullimage-20260921T212001Z/result.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def item(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def linux(path):
    path = Path(path).resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]


def inspect(path):
    with Path(path).open('rb') as stream:
        elf = ELFFile(stream)
        symbols = list(elf.get_section_by_name('.symtab').iter_symbols())
        imports = {s.name for s in symbols if s.name and s['st_shndx'] == 'SHN_UNDEF'}
        exports = {s.name[10:] for s in symbols if s.name.startswith('__ksymtab_')}
        info = {}
        for row in elf.get_section_by_name('.modinfo').data().split(b'\0'):
            if b'=' in row:
                key, value = row.decode().split('=', 1); info.setdefault(key, []).append(value)
        return imports, exports, info


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tests', type=Path, required=True)
    args = ap.parse_args()
    assert shutil.disk_usage(ROOT).free > 500*1024*1024
    assert shutil.disk_usage(Path('D:/')).free > 500*1024*1024
    tests = json.loads(args.tests.read_text()); base = json.loads(COMPONENTS.read_text()); image = json.loads(F364.read_text())
    assert tests['status'] == 'PASS_DIAGNOSTIC_NO_ADDITIONAL_SENSOR_IO'
    assert tests['source_sha256'] == sha(SOURCE/'temp_sens.c') and tests['diag_sha256'] == sha(SOURCE/'temp_diag.h')
    assert tests['core_sha256'] == sha(SOURCE/'topaz_temp_core.h') == 'cc86ae1c45828f66681d7eb8a78ea31955770d77135319e380e1987f5bb93a3c'
    assert image['schema'] == 'openmitrastar.f364r3-lifetime-image/v1'
    assert image['artifact']['sha256'] == sha(image['artifact']['path']) == 'ee6b7d09fd9e2dc5e0009d6756910510409ae13fb17108089a4caf7043056a15'
    assert base['status'] == 'PASS_OFFLINE_TEMPERATURE_INTEGRATION'
    for name in ('f363.config', 'f363.dtb', 'Module.symvers', 'a/sensor/temp_sens.ko'):
        assert sha(base['artifacts'][name]['path']) == base['artifacts'][name]['sha256']
    directory = Path(image['artifact']['path']).parent
    prefix = Path(image['artifact']['path']).name.removesuffix('.webformat.bin')
    assert sha(directory/(prefix+'.config')) == base['artifacts']['f363.config']['sha256']
    assert sha(directory/(prefix+'.dtb')) == base['artifacts']['f363.dtb']['sha256']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = Path('/workspace/OpenMitraStar-build/f365')/('f365-diagnostic-module-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SOURCE, out/'source')
    pins = {str(path): sha(path) for path in SOURCE.iterdir() if path.is_file()}
    src = base['kernel_source_linux']; original_kout = base['kernel_build_directory_linux']
    tc = linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    quote = shlex.quote
    script = f'''set -eu
out={quote(linux(out))}
src={quote(src)}
tc={quote(tc)}
kout="$out/kernel-context"
cp -a --reflink=auto {quote(original_kout)} "$kout"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {base['artifacts']['f363.config']['sha256']}
test "$(sha256sum "$kout/Module.symvers" | cut -d' ' -f1)" = {base['artifacts']['Module.symvers']['sha256']}
for lane in a b; do
 cp -a "$out/source" "$out/$lane"
 SOURCE_DATE_EPOCH=1790006400 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane" KCFLAGS="-ffile-prefix-map=$out/$lane=/f365-sensor" -j2 modules > "$out/build-$lane.log" 2>&1
done
cmp "$out/a/temp_sens.ko" "$out/b/temp_sens.ko"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {base['artifacts']['f363.config']['sha256']}
test "$(sha256sum "$kout/Module.symvers" | cut -d' ' -f1)" = {base['artifacts']['Module.symvers']['sha256']}
'''
    (out/'build.sh').write_bytes(script.encode())
    print(json.dumps(dict(build_started=str(out), hardware_actions=False)), flush=True)
    run = subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
    (out/'stdout').write_bytes(run.stdout); (out/'stderr').write_bytes(run.stderr)
    if run.returncode:
        (out/'result.json').write_text(json.dumps(dict(status='FAIL_MODULE_BUILD', hardware_actions=False, returncode=run.returncode),indent=2)+'\n')
        raise SystemExit('F365 module build failed: '+str(out))
    module = out/'a/temp_sens.ko'
    imports, exports, info = inspect(module)
    _, old_exports, old_info = inspect(base['artifacts']['a/sensor/temp_sens.ko']['path'])
    assert exports == old_exports == {'topaz_read_internal_temp_sens'}
    assert info['version'] == ['363'] and info['diagnostic_revision'] == ['365']
    assert info['license'] == old_info['license'] == ['GPL']
    assert info['vermagic'] == old_info['vermagic'] and info['depends'] == old_info['depends']
    available = {line.split()[1] for line in Path(base['artifacts']['Module.symvers']['path']).read_text().splitlines() if line.strip()}
    assert imports <= available, sorted(imports-available)
    assert sha(module) == sha(out/'b/temp_sens.ko')
    for path, digest in pins.items():
        assert sha(path) == digest and sha(out/'source'/Path(path).name) == digest
    result = dict(schema='openmitrastar.f365-temperature-diagnostic-module/v1',
        status='PASS_OFFLINE_CACHED_DATA_DIAGNOSTIC_MODULE', artifact=item(module), source_pins=pins,
        tests={**item(args.tests), 'status':tests['status']}, f364r3_image_result=item(F364),
        kernel_components=item(COMPONENTS), module_version='363', diagnostic_revision='365',
        f339_core_sha256=sha(SOURCE/'topaz_temp_core.h'), reproducible=True,
        kernel_recompiled=False, qdrv_recompiled=False, hardware_actions=False,
        extra_sensor_mmio=False, startup_sequence_changed=False, mask_or_timeout_changed=False,
        imports_resolved=sorted(imports), exports=sorted(exports), modinfo=info,
        sysfs_attributes=['diag_hwmon','diag_legacy'],
        diagnostic_schema='openmitrastar.f365-temperature-access/v1',
        clock_policy='two monotonic timestamp calls per actual access wrapper; diagnostic sysfs reads no clock or sensor',
        kernel_source_readonly=src, isolated_kernel_context=str(out/'kernel-context'))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({**result,'result':str(out/'result.json')},indent=2))


if __name__ == '__main__':
    main()
