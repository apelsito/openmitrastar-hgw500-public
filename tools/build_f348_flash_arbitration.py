"""Build F348 reader arbitration in a fresh F340 clone. No hardware operations."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shlex, subprocess
from elftools.elf.elffile import ELFFile
from build_f340_watchdog_kernel import extract_embedded
import f340_watchdog_contract as c

BASE = '/home/user/openmitrastar-build/f340-watchdog-20260921T132951Z/linux'
STAGE = c.DEVICE / 'analysis/f340-watchdog-kernel-20260921T132951Z'
OVERLAY = c.ROOT / 'work/kernel-port/versions/f348-flash-arbitration'
FILES = ['drivers/mtd/chips/map_rom.c', 'drivers/mtd/maps/physmap-core.c',
         'drivers/mtd/chips/qtn_topaz_flash_guard_core.inc',
         'include/linux/mtd/qtn_topaz_flash_guard.h']
BASE_PINS = {
    'drivers/mtd/chips/map_rom.c': '472b50706a948d09e858e0c1360ea1052adfaafc116c232daaf3946ecceff2e4',
    'drivers/mtd/maps/physmap-core.c': 'e8a17f67cdd48ec6aaedd20d8a928e0e034bacbbc9d802a3659bd304531cdbe0',
    'drivers/mtd/mtdchar.c': '3467dbaa76b809e2f4ba6bfec029ab654e9a298119a1c5e71a8db6d80ebc73ac',
}

def linux(p):
    p = Path(p).resolve()
    return '/mnt/' + p.drive[0].lower() + p.as_posix()[2:]

def item(p):
    return {'path': str(p), 'bytes': p.stat().st_size, 'sha256': c.sha(p)}

def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = c.DEVICE / 'analysis' / ('f348-flash-arbitration-' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    config = STAGE / 'a/f340.config'
    c.require(c.sha(config) == 'f374913b8d2adc7c4138af32263b650eeb967b4defc0139cfd00e6bff7ba1118', 'F340 config drift')
    required = ['CONFIG_MMU=y', 'CONFIG_MTD_ROM=y', 'CONFIG_MTD_PHYSMAP=y', '# CONFIG_OF_OVERLAY is not set']
    for line in required:
        c.require(line in config.read_text().splitlines(), 'unsupported mapping/lifetime profile: ' + line)
    (out / 'input.config').write_bytes(config.read_bytes())
    for name in FILES:
        dst = out / 'overlay' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((OVERLAY / name).read_bytes())
    build = '/home/user/openmitrastar-build/f348-flash-arbitration-' + stamp
    tc = linux(c.ROOT / 'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    q = shlex.quote
    script = f'''set -eu
out={q(linux(out))}
base={q(BASE)}
build={q(build)}
tc={q(tc)}
test ! -e "$build"
'''
    for name, digest in BASE_PINS.items():
        script += f'test "$(sha256sum "$base/{name}" | cut -d\' \' -f1)" = {digest}\n'
    script += '''mkdir -p "$build"
cp -a --reflink=auto "$base" "$build/linux"
src="$build/linux"
cp -a "$out/overlay/." "$src/"
diff -qr "$base" "$src" > "$out/source-delta.txt" || test "$?" = 1
'''
    script += f'''for lane in a b; do
kout="$build/$lane"
mkdir "$kout" "$out/$lane"
cp "$out/input.config" "$kout/.config"
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" olddefconfig > "$out/config-$lane.log" 2>&1
cmp "$out/input.config" "$kout/.config"
SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f348-flash-arbitration KBUILD_BUILD_VERSION=348 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=$kout=/f348-output" -j4 vmlinux dtbs uImage.bin > "$out/build-$lane.log" 2>&1
cp "$kout/vmlinux" "$out/$lane/f348.vmlinux"
if [ -f "$kout/Module.symvers" ]; then cp "$kout/Module.symvers" "$out/$lane/Module.symvers"; else cp "$kout/vmlinux.symvers" "$out/$lane/Module.symvers"; fi
cp "$kout/.config" "$out/$lane/f348.config"
cp "$kout/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$out/$lane/f348.dtb"
cp "$kout/arch/arc/boot/uImage.bin" "$out/$lane/f348.uncompressed.uImage"
"${{tc}}objcopy" -O binary -R .note -R .note.gnu.build-id -R .comment -S "$out/$lane/f348.vmlinux" "$out/$lane/f348.raw.bin"
done
cmp "$out/a/f348.vmlinux" "$out/b/f348.vmlinux"
cmp "$out/a/f348.raw.bin" "$out/b/f348.raw.bin"
cmp "$out/a/f348.dtb" "$out/b/f348.dtb"
cmp "$out/a/Module.symvers" "$out/b/Module.symvers"
'''
    (out / 'build.sh').write_bytes(script.encode())
    print(json.dumps({'build_started': str(out), 'isolated_source': build + '/linux', 'hardware_actions': False}), flush=True)
    run = subprocess.run(['wsl.exe', '-d', 'podman-mem9-tidb', '-u', 'root', '-e', 'sh', linux(out / 'build.sh')], stdin=subprocess.DEVNULL, capture_output=True)
    (out / 'launcher.stdout').write_bytes(run.stdout)
    (out / 'launcher.stderr').write_bytes(run.stderr)
    report = {'schema': 'openmitrastar.f348-flash-arbitration-kernel/v1', 'created_utc': stamp,
              'status': 'BUILD_FAILED', 'exit_code': run.returncode, 'isolated_source': build + '/linux',
              'build_directories': [build + '/a', build + '/b'], 'base_source': BASE,
              'hardware_actions': False, 'flash_write_api': False, 'flash_eligible': False,
              'rootfs_bundled': False, 'physical_gates': 'UNRUN', 'base_pins': BASE_PINS,
              'sources': [item(OVERLAY / name) for name in FILES] + [item(Path(__file__))]}
    if run.returncode == 0:
        dtb, address = extract_embedded(out / 'a/f348.vmlinux')
        c.require(dtb == (out / 'a/f348.dtb').read_bytes(), 'embedded DT sidecar drift')
        c.require(dtb == (STAGE / 'a/f340.dtb').read_bytes(), 'F340 DT changed')
        symbols = (out / 'a/Module.symvers').read_text().splitlines()
        expected = {'qtn_topaz_flash_claim', 'qtn_topaz_flash_release', 'qtn_topaz_flash_read_store'}
        exports = [line for line in symbols if len(line.split()) > 1 and line.split()[1] in expected]
        c.require(len(exports) == 3 and all('EXPORT_SYMBOL_GPL' in line for line in exports), 'GPL export contract')
        delta = (out / 'source-delta.txt').read_text().splitlines()
        c.require(len(delta) == 4, 'unexpected number of source changes')
        for name in FILES:
            c.require(any(name in line or (Path(name).name in line and str(Path(name).parent).replace('\\', '/') in line) for line in delta), 'source delta missing ' + name)
        with (out / 'a/f348.vmlinux').open('rb') as f:
            elf = ELFFile(f)
            entry = int(elf.header['e_entry'])
            end = int(elf.get_section_by_name('.symtab').get_symbol_by_name('_end')[0]['st_value'])
        c.require(entry == c.ENTRY and end < c.DDR_END, 'kernel bounds drift')
        report.update(status='PASS_OFFLINE_READER_ARBITRATION_KERNEL', reproducible=True,
                      config_byte_identical_to_f340=True, dt_byte_identical_to_f340=True,
                      base_dt_marker_retained=True, kernel_build_identity=348, exports=exports,
                      embedded_dtb_address=hex(address), kernel_entry=hex(entry), kernel_end=hex(end),
                      source_delta=delta, artifacts={p.name: item(p) for p in sorted((out / 'a').iterdir())})
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'result': str(out / 'result.json')}), flush=True)
    return 0 if report['status'].startswith('PASS_') else 1

if __name__ == '__main__':
    raise SystemExit(main())
