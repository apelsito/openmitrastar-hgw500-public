#!/usr/bin/env python3
"""Build and audit the F302 fail-closed Quantenna radar ABI provider."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f302_radar_native_fail_closed"
OUT = ROOT / "outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample"
BUILD_A = "/home/user/openmitrastar-build/f302-radar-native-a"
BUILD_B = "/home/user/openmitrastar-build/f302-radar-native-b"
QDRV_LINK_BUILD = "/home/user/openmitrastar-build/f302-qdrv-provider-link-probe"
EXPECTED_RELEASE = "5.10.260-openmitrastar-radiohw"
EXPECTED_CONFIG_SHA256 = "cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e"
EXPECTED_VMLINUX_SHA256 = "8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc"
EXPECTED_SYMVERS_SHA256 = "29e86facebed934166e4c52bf9e0a95972d677d49b0bc4e0a49df19e8b7c1269"
EXPECTED_VERMAGIC = f"{EXPECTED_RELEASE} mod_unload ARC700"
EXPECTED_F301_QDRV_SHA256 = "0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff"
EXPECTED_OEM_RADAR_SHA256 = "3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332"
EXPECTED_API = (
    "detect_drv_sample_loc_get",
    "dfs_rqmt_code",
    "radar_disable",
    "radar_enable",
    "radar_get_chan",
    "radar_get_status",
    "radar_ocac_info_addr_get",
    "radar_record_buffer_pt",
    "radar_register",
    "radar_register_is_dfs_chan",
    "radar_register_is_dfs_weather_chan",
    "radar_register_statcb",
    "radar_set_bw",
    "radar_set_chan",
    "radar_set_shared_params",
    "radar_start",
    "radar_stop",
    "sta_dfs_is_region_required",
)
EXPECTED_QDRV_IMPORTS = tuple(
    symbol for symbol in EXPECTED_API
    if symbol not in {"radar_get_chan", "radar_set_shared_params"}
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_wsl(shell: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", shell],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def main() -> int:
    provider_source = (SOURCE / "qtn_radar_native_f302.c").read_text(encoding="ascii")
    consumer_source = (SOURCE / "qtn_radar_native_f302_consumer_probe.c").read_text(encoding="ascii")
    compat_source = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_radar_compat.c").read_text(encoding="ascii")
    radar_header = (ROOT / "work/sources/Quantenna-GPL/drivers/radar/radar.h").read_text(encoding="ascii")

    forbidden = (
        "ioremap", "iounmap", "readl", "writel", "request_irq", "free_irq",
        "proc_create", "debugfs_create", "timer_setup", "schedule_work",
        "schedule_delayed_work", "mod_timer", "qtn_mproc_sync_shared_params_get",
    )
    for marker in forbidden:
        if marker in provider_source:
            raise SystemExit(f"F302 fail-closed provider contains forbidden active primitive: {marker}")
    for marker in (
        'return false;', 'return DFS_RQMT_UNKNOWN;', 'return -EOPNOTSUPP;',
        'backend_ready=0', 'fail_closed=1', 'EXPORT_SYMBOL(radar_start);',
    ):
        if marker not in provider_source:
            raise SystemExit(f"F302 safety contract missing: {marker}")

    for symbol in EXPECTED_API:
        if symbol not in provider_source:
            raise SystemExit(f"provider source missing radar API symbol: {symbol}")
        if symbol not in consumer_source:
            raise SystemExit(f"consumer probe missing radar API symbol: {symbol}")
        if symbol not in compat_source:
            raise SystemExit(f"F301 qdrv compat source missing expected API symbol: {symbol}")
        if symbol not in radar_header and symbol != "detect_drv_sample_loc_get":
            raise SystemExit(f"OEM radar header missing expected API symbol: {symbol}")

    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable evidence directory: {OUT}")
    OUT.mkdir(parents=True)
    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    source_wsl = f"{WS_ROOT}/{SOURCE.relative_to(ROOT).as_posix()}"
    qtn_gpl = f"{WS_ROOT}/work/sources/Quantenna-GPL"
    qdrv_compat = f"{WS_ROOT}/work/linux510-radio-port/quantenna/qdrv/compat/include"
    qdrv_source = f"{WS_ROOT}/work/linux510-radio-port/quantenna/qdrv"
    qtn_module_symvers = f"{WS_ROOT}/work/linux510-radio-port/quantenna/Module.symvers"
    f301_rootfs = "/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f301-device-bound/openmitrastar-linux510-f301-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.rootfs.squashfs"
    oem_radar = f"{WS_ROOT}/work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/radar/radar.ko"
    tc = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

    shell = rf"""
set -eu
src={shlex.quote(KERNEL_SRC)}
kout={shlex.quote(KERNEL_OUT)}
source={shlex.quote(source_wsl)}
out={shlex.quote(out_wsl)}
qtn_gpl={shlex.quote(qtn_gpl)}
qdrv_compat={shlex.quote(qdrv_compat)}
tc={shlex.quote(tc)}
build_a={shlex.quote(BUILD_A)}
build_b={shlex.quote(BUILD_B)}
qdrv_link_build={shlex.quote(QDRV_LINK_BUILD)}
qdrv_source={shlex.quote(qdrv_source)}
qtn_module_symvers={shlex.quote(qtn_module_symvers)}
f301_rootfs={shlex.quote(f301_rootfs)}
oem_radar={shlex.quote(oem_radar)}

test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {EXPECTED_CONFIG_SHA256}
test "$(sha256sum "$kout/vmlinux" | cut -d' ' -f1)" = {EXPECTED_VMLINUX_SHA256}
test "$(sha256sum "$kout/Module.symvers" | cut -d' ' -f1)" = {EXPECTED_SYMVERS_SHA256}
test "$(make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)" = {EXPECTED_RELEASE}
grep -qx '# CONFIG_MODVERSIONS is not set' "$kout/.config"
grep -qx 'CONFIG_MODULE_UNLOAD=y' "$kout/.config"

build_one() {{
    build="$1"
    rm -rf "$build"
    mkdir -p "$build"
    cp "$source/Makefile" "$source/qtn_radar_native_f302.c" \
        "$source/qtn_radar_native_f302_consumer_probe.c" "$build/"
    SOURCE_DATE_EPOCH=1785024000 \
    KBUILD_BUILD_TIMESTAMP=@1785024000 \
    KBUILD_BUILD_USER=openmitrastar \
    KBUILD_BUILD_HOST=builder \
    KBUILD_BUILD_VERSION=1 \
    make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" \
        M="$build" QTN_GPL="$qtn_gpl" QDRV_COMPAT="$qdrv_compat" modules
}}

build_one "$build_a" >"$out/build-a.log" 2>&1
build_one "$build_b" >"$out/build-b.log" 2>&1
cmp "$build_a/qtn_radar_native_f302.ko" "$build_b/qtn_radar_native_f302.ko"
cmp "$build_a/qtn_radar_native_f302_consumer_probe.ko" \
    "$build_b/qtn_radar_native_f302_consumer_probe.ko"
cp "$build_a/qtn_radar_native_f302.ko" "$out/"
cp "$build_a/qtn_radar_native_f302_consumer_probe.ko" "$out/"
cp "$build_a/Module.symvers" "$out/provider-Module.symvers"

modinfo "$out/qtn_radar_native_f302.ko" >"$out/provider-modinfo.txt"
modinfo "$out/qtn_radar_native_f302_consumer_probe.ko" >"$out/consumer-modinfo.txt"
"${{tc}}readelf" -h -S "$out/qtn_radar_native_f302.ko" >"$out/provider-readelf.txt"
"${{tc}}objdump" -dr "$out/qtn_radar_native_f302.ko" >"$out/provider-objdump.txt"
strings "$out/qtn_radar_native_f302.ko" >"$out/provider-strings.txt"
"${{tc}}nm" -u "$out/qtn_radar_native_f302.ko" | awk '{{print $2}}' | sort -u >"$out/provider-imports.txt"
"${{tc}}readelf" -p __ksymtab_strings "$out/qtn_radar_native_f302.ko" 2>/dev/null | \
    sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | sort -u >"$out/provider-exports.txt"
"${{tc}}nm" -u "$out/qtn_radar_native_f302_consumer_probe.ko" | awk '{{print $2}}' | sort -u >"$out/consumer-imports.txt"

test "$(modinfo -F vermagic "$out/qtn_radar_native_f302.ko")" = {shlex.quote(EXPECTED_VERMAGIC)}
test "$(modinfo -F vermagic "$out/qtn_radar_native_f302_consumer_probe.ko")" = {shlex.quote(EXPECTED_VERMAGIC)}
test "$(modinfo -F depends "$out/qtn_radar_native_f302.ko")" = ''
test "$(modinfo -F depends "$out/qtn_radar_native_f302_consumer_probe.ko")" = qtn_radar_native_f302
grep -q 'Machine:.*ARC' "$out/provider-readelf.txt"
grep -q 'OMF302RADAR loaded abi=1 backend_ready=0 fail_closed=1' "$out/provider-strings.txt"

for symbol in {' '.join(EXPECTED_API)}; do
    grep -qx "$symbol" "$out/provider-exports.txt"
    grep -qx "$symbol" "$out/consumer-imports.txt"
done
if grep -Eq 'ioremap|iounmap|readl|writel|request_irq|free_irq|proc_|debugfs|schedule|timer|mtd_|spi_' "$out/provider-imports.txt"; then
    echo 'F302 provider imports an active hardware or scheduler primitive' >&2
    cat "$out/provider-imports.txt" >&2
    exit 1
fi

: >"$out/provider-import-contract.txt"
while IFS= read -r symbol; do
    test -n "$symbol" || continue
    if grep -q "[[:space:]]$symbol[[:space:]]" "$kout/Module.symvers"; then
        printf '%s=EXPORTED_BY_EXACT_F301_KERNEL\n' "$symbol"
    else
        printf '%s=MISSING\n' "$symbol"
        exit 1
    fi
done <"$out/provider-imports.txt" >"$out/provider-import-contract.txt"

# Prove the linkage state of the exact F301 qdrv binary.
unsquashfs -cat "$f301_rootfs" \
    lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko \
    >/tmp/f301-qdrv-exact.ko
test "$(sha256sum /tmp/f301-qdrv-exact.ko | cut -d' ' -f1)" = {EXPECTED_F301_QDRV_SHA256}
modinfo /tmp/f301-qdrv-exact.ko >"$out/f301-qdrv-modinfo.txt"
"${{tc}}nm" -u /tmp/f301-qdrv-exact.ko | awk '{{print $2}}' | sort -u \
    >"$out/f301-qdrv-imports.txt"
"${{tc}}nm" -g --defined-only /tmp/f301-qdrv-exact.ko | awk '{{print $2"\t"$3}}' \
    >"$out/f301-qdrv-global-definitions.txt"
"${{tc}}readelf" -p __ksymtab_strings /tmp/f301-qdrv-exact.ko 2>/dev/null | \
    sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | sort -u \
    >"$out/f301-qdrv-exports.txt"
for symbol in {' '.join(EXPECTED_API)}; do
    grep -Eq "^[A-Za-z][[:space:]]+$symbol$" "$out/f301-qdrv-global-definitions.txt"
    ! grep -qx "$symbol" "$out/f301-qdrv-imports.txt"
    ! grep -qx "$symbol" "$out/f301-qdrv-exports.txt"
done

# Compile the current qdrv source in an isolated tree with its internal compat
# object removed. This is a link probe only and is never packaged or loaded.
rm -rf "$qdrv_link_build"
mkdir -p "$qdrv_link_build/qdrv" "$qdrv_link_build/wlan"
cp -a "$qdrv_source/." "$qdrv_link_build/qdrv/"
cp "$qdrv_source/../wlan/openmitrastar_beacon_preflight.h" "$qdrv_link_build/wlan/"
find "$qdrv_link_build" -type f \( -name '*.o' -o -name '*.ko' -o -name '*.mod' \
    -o -name '*.mod.c' -o -name '*.mod.o' -o -name modules.order \
    -o -name Module.symvers \) -delete
sed -i 's/qdrv_kernel_compat\.o qdrv_radar_compat\.o/qdrv_kernel_compat.o/' \
    "$qdrv_link_build/qdrv/Makefile"
! grep -q 'qdrv_radar_compat\.o' "$qdrv_link_build/qdrv/Makefile"
awk '$3 !~ /\/qdrv\/qdrv$/ {{print}}' "$qtn_module_symvers" \
    >"$qdrv_link_build/quantenna-dependencies.symvers"
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" \
    M="$qdrv_link_build/qdrv" QTN_GPL="$qtn_gpl" \
    KBUILD_EXTRA_SYMBOLS="$qdrv_link_build/quantenna-dependencies.symvers $build_a/Module.symvers" \
    KBUILD_MODPOST_WARN=1 -j12 modules >"$out/qdrv-external-provider-link-probe.log" 2>&1
! grep -Eq 'ERROR: modpost|undefined!' "$out/qdrv-external-provider-link-probe.log"
"${{tc}}nm" -u "$qdrv_link_build/qdrv/qdrv.ko" | awk '{{print $2}}' | sort -u \
    >"$out/qdrv-external-provider-imports.txt"
modinfo "$qdrv_link_build/qdrv/qdrv.ko" >"$out/qdrv-external-provider-modinfo.txt"
test "$(modinfo -F vermagic "$qdrv_link_build/qdrv/qdrv.ko")" = {shlex.quote(EXPECTED_VERMAGIC)}
case ",$(modinfo -F depends "$qdrv_link_build/qdrv/qdrv.ko")," in
    *,qtn_radar_native_f302,*) ;;
    *) echo 'externalized qdrv does not depend on qtn_radar_native_f302' >&2; exit 1 ;;
esac
for symbol in {' '.join(EXPECTED_QDRV_IMPORTS)}; do
    grep -qx "$symbol" "$out/qdrv-external-provider-imports.txt"
done
! grep -qx radar_get_chan "$out/qdrv-external-provider-imports.txt"
! grep -qx radar_set_shared_params "$out/qdrv-external-provider-imports.txt"

# Preserve the binary-only OEM boundary and show which 2.6.35 imports no
# longer have a loadable provider in the exact F301 kernel/module set.
test "$(sha256sum "$oem_radar" | cut -d' ' -f1)" = {EXPECTED_OEM_RADAR_SHA256}
modinfo "$oem_radar" >"$out/oem-radar-modinfo.txt"
"${{tc}}nm" -u "$oem_radar" | awk '{{print $2}}' | sort -u >"$out/oem-radar-imports.txt"
"${{tc}}readelf" -p __ksymtab_strings "$oem_radar" 2>/dev/null | \
    sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | sort -u \
    >"$out/oem-radar-exports.txt"
"${{tc}}readelf" -sW "$oem_radar" | \
    grep -E ' (radar_start|radar_stop|radar_enable|radar_disable|radar_set_chan|radar_set_bw|dfs_rqmt_code|detect_radar|detect_radar_poll|init_module|cleanup_module)$' \
    >"$out/oem-radar-function-sizes.txt"
for symbol in {' '.join(EXPECTED_QDRV_IMPORTS)}; do
    grep -qx "$symbol" "$out/oem-radar-exports.txt"
done
! grep -qx radar_get_chan "$out/oem-radar-exports.txt"
! grep -qx radar_set_shared_params "$out/oem-radar-exports.txt"

rm -rf /tmp/f301-radar-provider-root
unsquashfs -d /tmp/f301-radar-provider-root -no-xattrs "$f301_rootfs" >/dev/null
awk '{{print $2"\tvmlinux"}}' "$kout/Module.symvers" > /tmp/f301-radar-all-exports.tsv
find /tmp/f301-radar-provider-root -type f -name '*.ko' | while IFS= read -r module; do
    {{ "${{tc}}readelf" -p __ksymtab_strings "$module" 2>/dev/null || true; }} | \
        sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | while IFS= read -r symbol; do
            test -n "$symbol" && printf '%s\t%s\n' "$symbol" "$module"
        done
done >> /tmp/f301-radar-all-exports.tsv
printf 'symbol\tprovider\n' >"$out/oem-radar-import-provider-map.tsv"
while IFS= read -r symbol; do
    providers=$(awk -F '\t' -v wanted="$symbol" '$1 == wanted {{print $2}}' \
        /tmp/f301-radar-all-exports.tsv | paste -sd, -)
    test -n "$providers" || providers=MISSING
    printf '%s\t%s\n' "$symbol" "$providers"
done <"$out/oem-radar-imports.txt" >>"$out/oem-radar-import-provider-map.tsv"
"""
    proc = run_wsl(shell)
    (OUT / "build-command.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (OUT / "build-command.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)

    provider = OUT / "qtn_radar_native_f302.ko"
    consumer = OUT / "qtn_radar_native_f302_consumer_probe.ko"
    exports = tuple(line.strip() for line in (OUT / "provider-exports.txt").read_text(encoding="ascii").splitlines() if line.strip())
    imports = tuple(line.strip() for line in (OUT / "provider-imports.txt").read_text(encoding="ascii").splitlines() if line.strip())
    consumer_imports = tuple(line.strip() for line in (OUT / "consumer-imports.txt").read_text(encoding="ascii").splitlines() if line.strip())
    qdrv_imports = tuple(line.strip() for line in (OUT / "qdrv-external-provider-imports.txt").read_text(encoding="ascii").splitlines() if line.strip())
    oem_import_map = {}
    for line in (OUT / "oem-radar-import-provider-map.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        symbol, provider_name = line.split("\t", 1)
        oem_import_map[symbol] = provider_name
    missing_oem_imports = sorted(symbol for symbol, provider_name in oem_import_map.items() if provider_name == "MISSING")
    manifest = {
        "schema": "openmitrastar.f302-radar-native-fail-closed-offline/v1",
        "classification": "OFFLINE_ABI_SKELETON_NOT_A_RADAR_DETECTOR",
        "status": "PASS",
        "target": {
            "device": "HGW-500BNA-QCv2 A2",
            "kernel_release": EXPECTED_RELEASE,
            "architecture": "ARC700 little-endian",
            "f301_config_sha256": EXPECTED_CONFIG_SHA256,
            "f301_vmlinux_sha256": EXPECTED_VMLINUX_SHA256,
            "f301_module_symvers_sha256": EXPECTED_SYMVERS_SHA256,
            "modversions": False,
        },
        "provider": {
            "file": provider.name,
            "bytes": provider.stat().st_size,
            "sha256": sha256(provider),
            "vermagic": EXPECTED_VERMAGIC,
            "exports": list(exports),
            "imports": list(imports),
            "reproducible_two_builds": True,
        },
        "consumer_link_probe": {
            "file": consumer.name,
            "bytes": consumer.stat().st_size,
            "sha256": sha256(consumer),
            "imports_all_expected_api": all(symbol in consumer_imports for symbol in EXPECTED_API),
            "loadable_by_design": False,
            "init_result": "-EOPNOTSUPP",
        },
        "qdrv_contract": {
            "header_api_symbol_count": len(EXPECTED_API),
            "header_api_symbols": list(EXPECTED_API),
            "binary_link_symbol_count": len(EXPECTED_QDRV_IMPORTS),
            "binary_link_symbols": list(EXPECTED_QDRV_IMPORTS),
            "f301_qdrv_currently_links_internal_compat": True,
            "f301_qdrv_currently_imports_provider": False,
            "f301_qdrv_sha256": EXPECTED_F301_QDRV_SHA256,
            "current_source_externalized_link_probe": "PASS",
            "current_source_externalized_import_count": len(EXPECTED_QDRV_IMPORTS),
            "current_source_externalized_imports": list(EXPECTED_QDRV_IMPORTS),
            "current_source_externalized_all_imports_present": all(symbol in qdrv_imports for symbol in EXPECTED_QDRV_IMPORTS),
            "unused_oem_api_exports": ["radar_get_chan", "radar_set_shared_params"],
            "integration_required_later": "remove qdrv_radar_compat.o and link qdrv against this provider after a real detector exists",
        },
        "oem_radar_binary": {
            "sha256": EXPECTED_OEM_RADAR_SHA256,
            "vermagic": "2.6.35.12 mod_unload ARC700",
            "license": "Proprietary",
            "depends": ["qtn_debug", "bootcfg"],
            "exports_complete_16_symbol_qdrv_contract": True,
            "does_not_export_header_only_symbols": ["radar_get_chan", "radar_set_shared_params"],
            "import_count": len(oem_import_map),
            "imports_missing_from_f301": missing_oem_imports,
            "direct_reuse_on_f301": False,
        },
        "behavior": {
            "backend_ready": False,
            "radar_start": False,
            "radar_get_status": False,
            "dfs_rqmt_code": "DFS_RQMT_UNKNOWN",
            "registration": "-EOPNOTSUPP",
            "channel_set": "-EOPNOTSUPP",
            "mmio": False,
            "irq": False,
            "timers_or_workers": False,
        },
        "critical_blockers": [
            "the GPL drop contains radar.h and detect.h but no detector implementation source",
            "the OEM radar.ko is proprietary and built for Linux 2.6.35.12",
            "the hardware pulse FIFO, interrupt acknowledge and calibrated detector behavior are not yet evidenced on Linux 5.10",
            "F301 qdrv embeds qdrv_radar_compat and therefore cannot consume a separate provider without a later qdrv rebuild",
        ],
        "safety": {
            "integrated_into_firmware": False,
            "module_loaded": False,
            "router_contacted": False,
            "uart": False,
            "tftp": False,
            "flash": False,
            "mtd_write": False,
        },
        "physical_validation": "NOT_RUN",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
