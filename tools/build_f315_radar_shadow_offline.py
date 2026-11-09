#!/usr/bin/env python3
"""Build and audit the F315 native QT4 radar shadow provider offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f315_radar_shadow"
OUT = ROOT / "outputs/kernel-port/f315-radar-shadow-20260905"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample"
BUILD_A = "/home/user/openmitrastar-build/f315-radar-shadow-a"
BUILD_B = "/home/user/openmitrastar-build/f315-radar-shadow-b"
QDRV_LINK_BUILD = "/home/user/openmitrastar-build/f315-qdrv-provider-link-probe"
EXPECTED_RELEASE = "5.10.260-openmitrastar-radiohw"
EXPECTED_VERMAGIC = f"{EXPECTED_RELEASE} mod_unload ARC700"
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_wsl(shell: str, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash",
            "--noprofile", "--norc", "-c", shell,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def source_contract() -> dict[str, object]:
    main = (SOURCE / "qtn_radar_shadow_f315_main.c").read_text(encoding="ascii")
    core = (SOURCE / "f315_radar_core.c").read_text(encoding="ascii")
    header = (SOURCE / "f315_radar_core.h").read_text(encoding="ascii")
    source = main + core + header
    required = (
        "static bool shadow_enable;",
        "module_param(shadow_enable, bool, 0444);",
        "module_param(shadow_arm, bool, 0600);",
        "backend_ready=0",
        "fail_closed=1",
        "tx_authorization=denied",
        "callback_storage=0",
        "callback_allowed=0",
        "return false;",
        "return -EOPNOTSUPP;",
        "f315_value_allowed",
        "if (!shadow_enable || !f315_value_allowed(id, value))",
        "F315_ZC_WORDS 28U",
        "F315_MAX_PULSES 18U",
    )
    missing = [marker for marker in required if marker not in source]
    if missing:
        raise SystemExit(f"F315 source contract missing: {missing}")
    forbidden = (
        "qdrv_radar_detected", "mark_radar", "request_irq", "free_irq",
        ".proc_write", "/dev/mtd", "call_usermodehelper",
    )
    found = [marker for marker in forbidden if marker in source]
    if found:
        raise SystemExit(f"F315 source contains forbidden primitive: {found}")
    if "(*callback" in main or "(*dfs_mark_callback" in main:
        raise SystemExit("F315 must not store callback pointers")
    if main.count("writel(") != 2:
        raise SystemExit("F315 MMIO write primitives must remain confined to two guarded helpers")
    if "if (!shadow_enable || !f315_windows[F315_WINDOW_CAPTURE].base" not in main:
        raise SystemExit("F315 capture-memory writes lack the shadow_enable guard")
    for symbol in EXPECTED_API:
        if f"EXPORT_SYMBOL({symbol});" not in main:
            raise SystemExit(f"F315 source missing ABI export: {symbol}")
    return {
        "abi_exports": list(EXPECTED_API),
        "shadow_enable_default": False,
        "shadow_arm_default": False,
        "callback_pointer_stored": False,
        "callback_invocation_present": False,
        "radar_get_status": False,
        "radar_start": False,
        "writes_guarded_by_shadow_enable_and_allowlist": True,
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
            raise SystemExit(f"unsafe replacement target: {OUT}")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    source_wsl = f"{WS_ROOT}/{SOURCE.relative_to(ROOT).as_posix()}"
    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    qtn_gpl = f"{WS_ROOT}/work/sources/Quantenna-GPL"
    compat = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/compat/include"
    qtn_symvers = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/Module.symvers"
    qdrv_source = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv"
    tc = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

    shell = rf"""
set -eu
src={shlex.quote(KERNEL_SRC)}
kout={shlex.quote(KERNEL_OUT)}
source={shlex.quote(source_wsl)}
out={shlex.quote(out_wsl)}
qtn_gpl={shlex.quote(qtn_gpl)}
compat={shlex.quote(compat)}
qtn_symvers={shlex.quote(qtn_symvers)}
tc={shlex.quote(tc)}
build_a={shlex.quote(BUILD_A)}
build_b={shlex.quote(BUILD_B)}
qdrv_build={shlex.quote(QDRV_LINK_BUILD)}

test "$(make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)" = {EXPECTED_RELEASE}

host=/tmp/f315-radar-host-test
rm -rf "$host"
mkdir -p "$host"
cp "$source/f315_radar_core.c" "$source/f315_radar_core.h" "$source/test_f315_radar_core.c" "$host/"
cc -std=c99 -Wall -Wextra -Werror -O2 -o "$host/test_f315_radar_core" \
    "$host/test_f315_radar_core.c" "$host/f315_radar_core.c"
"$host/test_f315_radar_core" >"$out/host-tests.log"

build_one() {{
    build="$1"
    rm -rf "$build"
    mkdir -p "$build"
    cp "$source/Makefile" "$source"/*.c "$source"/*.h "$build/"
    SOURCE_DATE_EPOCH=1788530400 \
    KBUILD_BUILD_TIMESTAMP=@1788530400 \
    KBUILD_BUILD_USER=openmitrastar \
    KBUILD_BUILD_HOST=builder \
    KBUILD_BUILD_VERSION=1 \
    make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" \
        M="$build" QTN_GPL="$qtn_gpl" QDRV_COMPAT="$compat" \
        KBUILD_EXTRA_SYMBOLS="$qtn_symvers" modules
}}

build_one "$build_a" >"$out/build-a.log" 2>&1
build_one "$build_b" >"$out/build-b.log" 2>&1
! grep -q 'frame size' "$out/build-a.log" "$out/build-b.log"
cmp "$build_a/qtn_radar_shadow_f315.ko" "$build_b/qtn_radar_shadow_f315.ko"
cp "$build_a/qtn_radar_shadow_f315.ko" "$out/"
cp "$build_a/Module.symvers" "$out/provider-Module.symvers"

modinfo "$out/qtn_radar_shadow_f315.ko" >"$out/provider-modinfo.txt"
"${{tc}}readelf" -h -S "$out/qtn_radar_shadow_f315.ko" >"$out/provider-readelf.txt"
"${{tc}}objdump" -dr "$out/qtn_radar_shadow_f315.ko" >"$out/provider-objdump.txt"
strings "$out/qtn_radar_shadow_f315.ko" >"$out/provider-strings.txt"
"${{tc}}nm" -u "$out/qtn_radar_shadow_f315.ko" | awk '{{print $2}}' | sort -u >"$out/provider-imports.txt"
"${{tc}}readelf" -p __ksymtab_strings "$out/qtn_radar_shadow_f315.ko" 2>/dev/null | \
    sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | sort -u >"$out/provider-exports.txt"

test "$(modinfo -F vermagic "$out/qtn_radar_shadow_f315.ko")" = {shlex.quote(EXPECTED_VERMAGIC)}
grep -q 'Machine:.*ARC' "$out/provider-readelf.txt"
grep -q 'callback_invocations=0' "$out/provider-strings.txt"
grep -q 'callback_storage=0' "$out/provider-strings.txt"
grep -q 'callback_allowed=0' "$out/provider-strings.txt"
grep -q 'backend_ready=0' "$out/provider-strings.txt"
grep -q 'tx_authorization=denied' "$out/provider-strings.txt"
! grep -Eq 'qdrv_radar_detected|mark_radar' "$out/provider-imports.txt" "$out/provider-objdump.txt" "$out/provider-strings.txt"

for symbol in {' '.join(EXPECTED_API)}; do
    grep -qx "$symbol" "$out/provider-exports.txt"
done

: >"$out/provider-import-contract.txt"
while IFS= read -r symbol; do
    test -n "$symbol" || continue
    if grep -q "[[:space:]]$symbol[[:space:]]" "$kout/Module.symvers" || \
       grep -q "[[:space:]]$symbol[[:space:]]" "$qtn_symvers"; then
        printf '%s=RESOLVED\n' "$symbol"
    else
        printf '%s=MISSING\n' "$symbol"
        exit 1
    fi
done <"$out/provider-imports.txt" >"$out/provider-import-contract.txt"

rm -rf "$qdrv_build"
mkdir -p "$qdrv_build/qdrv" "$qdrv_build/wlan"
cp -a {shlex.quote(qdrv_source)}/. "$qdrv_build/qdrv/"
cp {shlex.quote(qdrv_source)}/../wlan/openmitrastar_beacon_preflight.h "$qdrv_build/wlan/"
find "$qdrv_build" -type f \( -name '*.o' -o -name '*.ko' -o -name '*.mod' \
    -o -name '*.mod.c' -o -name '*.mod.o' -o -name modules.order \
    -o -name Module.symvers \) -delete
sed -i 's/qdrv_kernel_compat\.o qdrv_radar_compat\.o/qdrv_kernel_compat.o/' "$qdrv_build/qdrv/Makefile"
! grep -q 'qdrv_radar_compat\.o' "$qdrv_build/qdrv/Makefile"
awk '$3 !~ /\/qdrv\/qdrv$/ {{print}}' "$qtn_symvers" >"$qdrv_build/quantenna-dependencies.symvers"
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" \
    M="$qdrv_build/qdrv" QTN_GPL="$qtn_gpl" \
    KBUILD_EXTRA_SYMBOLS="$qdrv_build/quantenna-dependencies.symvers $build_a/Module.symvers" \
    KBUILD_MODPOST_WARN=1 -j12 modules >"$out/qdrv-external-provider-link-probe.log" 2>&1
! grep -Eq 'ERROR: modpost|undefined!' "$out/qdrv-external-provider-link-probe.log"
"${{tc}}nm" -u "$qdrv_build/qdrv/qdrv.ko" | awk '{{print $2}}' | sort -u >"$out/qdrv-external-provider-imports.txt"
modinfo "$qdrv_build/qdrv/qdrv.ko" >"$out/qdrv-external-provider-modinfo.txt"
cp "$qdrv_build/qdrv/qdrv.ko" "$out/qdrv-f315-external-radar.ko"
case ",$(modinfo -F depends "$qdrv_build/qdrv/qdrv.ko")," in
    *,qtn_radar_shadow_f315,*) ;;
    *) echo 'externalized qdrv does not depend on qtn_radar_shadow_f315' >&2; exit 1 ;;
esac
for symbol in {' '.join(EXPECTED_QDRV_IMPORTS)}; do
    grep -qx "$symbol" "$out/qdrv-external-provider-imports.txt"
done
"""
    proc = run_wsl(shell)
    (OUT / "build-command.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (OUT / "build-command.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)

    provider = OUT / "qtn_radar_shadow_f315.ko"
    qdrv = OUT / "qdrv-f315-external-radar.ko"
    exports = tuple(
        line for line in (OUT / "provider-exports.txt").read_text(encoding="ascii").splitlines()
        if line
    )
    imports = tuple(
        line for line in (OUT / "provider-imports.txt").read_text(encoding="ascii").splitlines()
        if line
    )
    qdrv_imports = tuple(
        line for line in (OUT / "qdrv-external-provider-imports.txt").read_text(encoding="ascii").splitlines()
        if line
    )
    if exports != tuple(sorted(EXPECTED_API)):
        raise SystemExit(f"F315 export drift: {exports}")

    source_paths = tuple(sorted(SOURCE.glob("*.c"))) + tuple(sorted(SOURCE.glob("*.h"))) + (SOURCE / "Makefile",)
    manifest = {
        "schema": "openmitrastar.f315-radar-shadow-offline/v1",
        "date": "2026-09-05",
        "status": "PASS",
        "classification": "OFFLINE_NATIVE_SHADOW_PROVIDER_NOT_DFS_AUTHORITY",
        "target": {
            "device": "HGW-500BNA-QCv2 A2",
            "architecture": "ARC700 little-endian",
            "kernel_release": EXPECTED_RELEASE,
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
        "contract": contract,
        "tests": {"host_core": "PASS", "arc700_module": "PASS", "import_resolution": "PASS"},
        "qdrv_link_probe": {
            "status": "PASS",
            "internal_qdrv_radar_compat_removed": True,
            "provider_dependency": "qtn_radar_shadow_f315",
            "file": qdrv.name,
            "bytes": qdrv.stat().st_size,
            "sha256": sha256(qdrv),
            "resolved_imports": [symbol for symbol in EXPECTED_QDRV_IMPORTS if symbol in qdrv_imports],
        },
        "source_artifacts": [
            {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in source_paths
        ],
        "limits": [
            "Classifier output is shadow-only and not source-equivalent to the complete OEM classifier.",
            "Pulse ring and zero-crossing chronology require physical validation.",
            "The module has not been loaded on hardware and authorizes no DFS transmission.",
            "callback_invocations is structurally fixed at zero in F315.",
        ],
        "safety": {"router": False, "uart": False, "tftp": False, "flash": False, "mtd": False},
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="ascii"
    )
    print(json.dumps({
        "status": "PASS",
        "provider": str(provider),
        "bytes": provider.stat().st_size,
        "sha256": sha256(provider),
        "exports": len(exports),
        "imports": len(imports),
        "callback_invocations": 0,
        "hardware_actions": 0,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
