#!/usr/bin/env python3
"""Build and audit the F316 native QT4 radar provider offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f316_radar_native"
OUT = ROOT / "outputs/kernel-port/f316-radar-native-20260905"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample"
EXPECTED_RELEASE = "5.10.260-openmitrastar-radiohw"
EXPECTED_VERMAGIC = f"{EXPECTED_RELEASE} mod_unload ARC700"
EXPECTED_API = (
    "detect_drv_sample_loc_get", "dfs_rqmt_code", "radar_disable",
    "radar_enable", "radar_get_chan", "radar_get_status",
    "radar_ocac_info_addr_get", "radar_record_buffer_pt", "radar_register",
    "radar_register_is_dfs_chan", "radar_register_is_dfs_weather_chan",
    "radar_register_statcb", "radar_set_bw", "radar_set_chan",
    "radar_set_shared_params", "radar_start", "radar_stop",
    "sta_dfs_is_region_required",
)
EXPECTED_QDRV_IMPORTS = tuple(
    symbol for symbol in EXPECTED_API
    if symbol not in {"radar_get_chan", "radar_set_shared_params"}
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_wsl(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1200,
        check=False,
    )


def source_contract() -> dict[str, object]:
    main = (SOURCE / "qtn_radar_native_f316_main.c").read_text(encoding="ascii")
    required = (
        "module_param(authoritative_enable, bool, 0444);",
        "module_param(weather_enable, bool, 0444);",
        "module_param(ready, bool, 0444);",
        "f316_classifier_process",
        "f316_delivered_epoch != epoch",
        "f316_callback_inflight = true",
        "mutex_unlock(&f315_state_lock);\n\tif (callback)",
        "cancel_delayed_work(&f315_poll_work);",
        "cancel_delayed_work_sync(&f315_poll_work);",
        "return READ_ONCE(f316_enabled);",
    )
    missing = [marker for marker in required if marker not in main]
    if missing:
        raise SystemExit(f"F316 source contract missing: {missing}")
    forbidden = ("qdrv_radar_detected", "mark_radar", ".proc_write", "/dev/mtd")
    found = [marker for marker in forbidden if marker in main]
    if found:
        raise SystemExit(f"F316 provider contains forbidden coupling: {found}")
    for symbol in EXPECTED_API:
        if f"EXPORT_SYMBOL({symbol});" not in main:
            raise SystemExit(f"F316 missing radar ABI export: {symbol}")
    return {
        "abi_exports": list(EXPECTED_API),
        "authoritative_enable_default": False,
        "weather_enable_default": False,
        "callback_invocation_gated": True,
        "callback_outside_state_and_mmio_locks": True,
        "epoch_deduplication": True,
        "disable_nonblocking": True,
        "stop_synchronized": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    contract = source_contract()
    if OUT.exists():
        if not args.replace_existing:
            raise SystemExit(f"refusing to overwrite evidence directory: {OUT}")
        if OUT.resolve().parent != (ROOT / "outputs/kernel-port").resolve():
            raise SystemExit(f"unsafe output path: {OUT}")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    source_wsl = f"{WS_ROOT}/{SOURCE.relative_to(ROOT).as_posix()}"
    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    qtn = f"{WS_ROOT}/work/sources/Quantenna-GPL"
    compat = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/compat/include"
    qdrv_source = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv"
    qtn_symvers = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/Module.symvers"
    tc = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
    script = rf"""
set -eu
src={shlex.quote(KERNEL_SRC)}
kout={shlex.quote(KERNEL_OUT)}
source={shlex.quote(source_wsl)}
out={shlex.quote(out_wsl)}
qtn={shlex.quote(qtn)}
compat={shlex.quote(compat)}
qdrv_source={shlex.quote(qdrv_source)}
qtn_symvers={shlex.quote(qtn_symvers)}
tc={shlex.quote(tc)}
test "$(make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)" = {EXPECTED_RELEASE}

build_one() {{
    build="$1"
    rm -rf "$build"
    mkdir -p "$build"
    cp -a "$source"/. "$build"/
    find "$build" -type f \( -name '*.o' -o -name '*.ko' -o -name '*.mod' \
        -o -name '*.mod.c' -o -name '*.mod.o' -o -name modules.order \
        -o -name Module.symvers \) -delete
    SOURCE_DATE_EPOCH=1788566400 KBUILD_BUILD_TIMESTAMP=@1788566400 \
    KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \
    make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build" \
        QTN_GPL="$qtn" QDRV_COMPAT="$compat" KBUILD_EXTRA_SYMBOLS="$qtn_symvers" \
        KBUILD_MODPOST_WARN=1 -j12 modules
}}

build_one /home/user/openmitrastar-build/f316-radar-native-a >"$out/build-a.log" 2>&1
build_one /home/user/openmitrastar-build/f316-radar-native-b >"$out/build-b.log" 2>&1
! grep -q 'frame size' "$out/build-a.log" "$out/build-b.log"
cmp /home/user/openmitrastar-build/f316-radar-native-a/qtn_radar_native.ko \
    /home/user/openmitrastar-build/f316-radar-native-b/qtn_radar_native.ko
cp /home/user/openmitrastar-build/f316-radar-native-a/qtn_radar_native.ko "$out/"
cp /home/user/openmitrastar-build/f316-radar-native-a/Module.symvers "$out/provider-Module.symvers"
modinfo "$out/qtn_radar_native.ko" >"$out/provider-modinfo.txt"
"${{tc}}readelf" -h -S "$out/qtn_radar_native.ko" >"$out/provider-readelf.txt"
"${{tc}}objdump" -dr "$out/qtn_radar_native.ko" >"$out/provider-objdump.txt"
strings "$out/qtn_radar_native.ko" >"$out/provider-strings.txt"
"${{tc}}nm" -u "$out/qtn_radar_native.ko" | awk '{{print $2}}' | sort -u >"$out/provider-imports.txt"
"${{tc}}readelf" -p __ksymtab_strings "$out/qtn_radar_native.ko" 2>/dev/null | \
    sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | sort -u >"$out/provider-exports.txt"
test "$(modinfo -F vermagic "$out/qtn_radar_native.ko")" = {shlex.quote(EXPECTED_VERMAGIC)}
grep -q 'Machine:.*ARC' "$out/provider-readelf.txt"
grep -q 'authoritative_enable' "$out/provider-modinfo.txt"
grep -q 'weather_enable' "$out/provider-modinfo.txt"
for symbol in {' '.join(EXPECTED_API)}; do grep -qx "$symbol" "$out/provider-exports.txt"; done

qdrv=/home/user/openmitrastar-build/f316-qdrv-provider-link
rm -rf "$qdrv"
mkdir -p "$qdrv/qdrv" "$qdrv/wlan"
cp -a "$qdrv_source"/. "$qdrv/qdrv/"
cp "$qdrv_source/../wlan/openmitrastar_beacon_preflight.h" "$qdrv/wlan/"
find "$qdrv" -type f \( -name '*.o' -o -name '*.ko' -o -name '*.mod' \
    -o -name '*.mod.c' -o -name '*.mod.o' -o -name modules.order \
    -o -name Module.symvers \) -delete
sed -i 's/qdrv_kernel_compat\.o qdrv_radar_compat\.o/qdrv_kernel_compat.o/' "$qdrv/qdrv/Makefile"
awk '$3 !~ /\/qdrv\/qdrv$/ {{print}}' "$qtn_symvers" >"$qdrv/dependencies.symvers"
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$qdrv/qdrv" QTN_GPL="$qtn" \
    KBUILD_EXTRA_SYMBOLS="$qdrv/dependencies.symvers /home/user/openmitrastar-build/f316-radar-native-a/Module.symvers" \
    KBUILD_MODPOST_WARN=1 -j12 modules >"$out/qdrv-link.log" 2>&1
! grep -Eq 'ERROR: modpost|undefined!' "$out/qdrv-link.log"
modinfo "$qdrv/qdrv/qdrv.ko" >"$out/qdrv-modinfo.txt"
"${{tc}}nm" -u "$qdrv/qdrv/qdrv.ko" | awk '{{print $2}}' | sort -u >"$out/qdrv-imports.txt"
case ",$(modinfo -F depends "$qdrv/qdrv/qdrv.ko")," in
    *,qtn_radar_native,*) ;;
    *) exit 1 ;;
esac
for symbol in {' '.join(EXPECTED_QDRV_IMPORTS)}; do grep -qx "$symbol" "$out/qdrv-imports.txt"; done
cp "$qdrv/qdrv/qdrv.ko" "$out/qdrv-f316-external-radar.ko"
"""
    result = run_wsl(script)
    (OUT / "build.stdout.log").write_text(result.stdout, encoding="utf-8")
    (OUT / "build.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)

    provider = OUT / "qtn_radar_native.ko"
    qdrv = OUT / "qdrv-f316-external-radar.ko"
    exports = sorted((OUT / "provider-exports.txt").read_text(encoding="ascii").splitlines())
    if exports != sorted(EXPECTED_API):
        raise SystemExit("F316 radar ABI export drift")
    manifest = {
        "schema": "openmitrastar.f316-radar-native-offline/v1",
        "date": "2026-09-05",
        "status": "PASS",
        "classification": "ACTIVE_CAPABLE_PROVIDER_AUTHORITY_DEFAULT_OFF",
        "provider": {
            "file": provider.name,
            "bytes": provider.stat().st_size,
            "sha256": sha256(provider),
            "vermagic": EXPECTED_VERMAGIC,
            "exports": exports,
            "reproducible_two_builds": True,
        },
        "qdrv": {
            "file": qdrv.name,
            "bytes": qdrv.stat().st_size,
            "sha256": sha256(qdrv),
            "internal_radar_compat_removed": True,
            "external_provider_link": "PASS",
        },
        "contract": contract,
        "runtime_defaults": {
            "hardware_mapping": False,
            "authoritative_enable": False,
            "weather_enable": False,
            "ready": False,
            "callbacks": 0,
        },
        "limits": [
            "No physical F315 pulse/ZC chronology has been captured yet.",
            "Weather detection remains disabled pending physical vectors.",
            "This artifact is not yet a flash candidate.",
        ],
        "hardware_actions": {
            "router": False, "uart": False, "ssh": False,
            "tftp": False, "flash": False, "mtd": False,
        },
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
