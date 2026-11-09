#!/usr/bin/env python3
"""Build and audit the F308 bounded read-only Quantenna radar observer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f308_radar_observer"
OUT = ROOT / "outputs/kernel-port/f308-radar-observer-20260904"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample"
BUILD_A = "/home/user/openmitrastar-build/f308-radar-observer-a"
BUILD_B = "/home/user/openmitrastar-build/f308-radar-observer-b"
QDRV_LINK_BUILD = "/home/user/openmitrastar-build/f308-qdrv-provider-link-probe"
EXPECTED_RELEASE = "5.10.260-openmitrastar-radiohw"
EXPECTED_CONFIG_SHA256 = "cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e"
EXPECTED_VMLINUX_SHA256 = "8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc"
EXPECTED_SYMVERS_SHA256 = "29e86facebed934166e4c52bf9e0a95972d677d49b0bc4e0a49df19e8b7c1269"
EXPECTED_KERNEL_LZMA_SHA256 = "fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649"
EXPECTED_VERMAGIC = f"{EXPECTED_RELEASE} mod_unload ARC700"
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
EXPECTED_PROVIDER_IMPORTS = (
    "atomic64_add",
    "atomic64_read",
    "ioremap",
    "iounmap",
    "mutex_lock",
    "mutex_unlock",
    "param_ops_bool",
    "param_ops_uint",
    "printk",
    "proc_create",
    "proc_mkdir",
    "remove_proc_subtree",
    "seq_lseek",
    "seq_printf",
    "seq_puts",
    "seq_read",
    "single_open",
    "single_release",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="ascii"))


def run_wsl(shell: str, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", shell],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def source_contract() -> dict[str, object]:
    source = (SOURCE / "qtn_radar_observer_f308.c").read_text(encoding="ascii")
    forbidden = (
        "writel", "writeb", "writew", "iowrite", "memcpy_toio",
        "request_irq", "free_irq", "schedule_work", "schedule_delayed_work",
        "timer_setup", "mod_timer", "qdrv_radar_detected", "mark_radar",
        "call_usermodehelper", "spi_flash", "/dev/mtd", ".proc_write",
    )
    found = [marker for marker in forbidden if marker in source]
    if found:
        raise SystemExit(f"F308 source contains forbidden active primitive: {found}")
    required = (
        "return false;",
        "return DFS_RQMT_UNKNOWN;",
        "return -EOPNOTSUPP;",
        "backend_ready=0",
        "fail_closed=1",
        "samples_meaningful=0",
        "physical_rf_detection_proven=0",
        "rf_register_writes=0",
        "F308_MAX_SAMPLES 18U",
        "proc_create(\"status\", 0444",
        "proc_create(\"snapshot\", 0444",
        "readl(",
        "ioremap(",
    )
    missing = [marker for marker in required if marker not in source]
    if missing:
        raise SystemExit(f"F308 source contract missing: {missing}")
    for symbol in EXPECTED_API:
        if f"EXPORT_SYMBOL({symbol});" not in source:
            raise SystemExit(f"F308 source missing ABI export: {symbol}")
    return {
        "forbidden_primitive_count": 0,
        "abi_exports": list(EXPECTED_API),
        "callback_pointer_stored": False,
        "callback_invocation_present": False,
        "rf_write_primitive_present": False,
        "worker_or_irq_present": False,
        "observer_default": "disabled",
        "snapshot_limit": 18,
    }


def verify_firmware_lineage() -> dict[str, object]:
    private = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
    f301 = read_json(private / "f301-device-bound/manifest.json")
    f306 = read_json(private / "f306-device-bound/manifest.json")
    f301_kernel = f301["artifacts"]["kernel_lzma"]["sha256"]
    f306_kernel = f306["artifacts"]["kernel_lzma"]["sha256"]
    if f301_kernel != EXPECTED_KERNEL_LZMA_SHA256 or f306_kernel != f301_kernel:
        raise SystemExit("F301/F306 kernel lineage mismatch")
    if f306.get("source", {}).get("f301_kernel_lzma_sha256") != f301_kernel:
        raise SystemExit("F306 does not declare the exact F301 kernel")
    return {
        "f301_kernel_lzma_sha256": f301_kernel,
        "f306_kernel_lzma_sha256": f306_kernel,
        "byte_identical": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    contract = source_contract()
    lineage = verify_firmware_lineage()
    if OUT.exists():
        if not args.replace_existing:
            raise SystemExit(f"refusing to overwrite immutable evidence directory: {OUT}")
        expected_parent = (ROOT / "outputs/kernel-port").resolve()
        if OUT.resolve().parent != expected_parent or OUT.name != "f308-radar-observer-20260904":
            raise SystemExit(f"unsafe F308 replacement target: {OUT}")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    source_wsl = f"{WS_ROOT}/{SOURCE.relative_to(ROOT).as_posix()}"
    qtn_gpl = f"{WS_ROOT}/work/sources/Quantenna-GPL"
    compat = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/compat/include"
    qdrv_source = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv"
    qtn_symvers = f"{WS_ROOT}/work/linux510-radio-port/quantenna-v6-scheduler-diag/Module.symvers"
    tc = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

    shell = rf"""
set -eu
src={shlex.quote(KERNEL_SRC)}
kout={shlex.quote(KERNEL_OUT)}
source={shlex.quote(source_wsl)}
out={shlex.quote(out_wsl)}
qtn_gpl={shlex.quote(qtn_gpl)}
compat={shlex.quote(compat)}
qdrv_source={shlex.quote(qdrv_source)}
qtn_symvers={shlex.quote(qtn_symvers)}
tc={shlex.quote(tc)}
build_a={shlex.quote(BUILD_A)}
build_b={shlex.quote(BUILD_B)}
qdrv_build={shlex.quote(QDRV_LINK_BUILD)}

test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {EXPECTED_CONFIG_SHA256}
test "$(sha256sum "$kout/vmlinux" | cut -d' ' -f1)" = {EXPECTED_VMLINUX_SHA256}
test "$(sha256sum "$kout/Module.symvers" | cut -d' ' -f1)" = {EXPECTED_SYMVERS_SHA256}
test "$(make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)" = {EXPECTED_RELEASE}
grep -qx 'CONFIG_PROC_FS=y' "$kout/.config"
! grep -qx 'CONFIG_DEBUG_FS=y' "$kout/.config"

build_one() {{
    build="$1"
    rm -rf "$build"
    mkdir -p "$build"
    cp "$source/Makefile" "$source/qtn_radar_observer_f308.c" "$build/"
    SOURCE_DATE_EPOCH=1788480000 \
    KBUILD_BUILD_TIMESTAMP=@1788480000 \
    KBUILD_BUILD_USER=openmitrastar \
    KBUILD_BUILD_HOST=builder \
    KBUILD_BUILD_VERSION=1 \
    make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" \
        M="$build" QTN_GPL="$qtn_gpl" QDRV_COMPAT="$compat" modules
}}

build_one "$build_a" >"$out/build-a.log" 2>&1
build_one "$build_b" >"$out/build-b.log" 2>&1
cmp "$build_a/qtn_radar_observer_f308.ko" "$build_b/qtn_radar_observer_f308.ko"
cp "$build_a/qtn_radar_observer_f308.ko" "$out/"
cp "$build_a/Module.symvers" "$out/provider-Module.symvers"

modinfo "$out/qtn_radar_observer_f308.ko" >"$out/provider-modinfo.txt"
"${{tc}}readelf" -h -S "$out/qtn_radar_observer_f308.ko" >"$out/provider-readelf.txt"
"${{tc}}objdump" -dr "$out/qtn_radar_observer_f308.ko" >"$out/provider-objdump.txt"
strings "$out/qtn_radar_observer_f308.ko" >"$out/provider-strings.txt"
"${{tc}}nm" -u "$out/qtn_radar_observer_f308.ko" | awk '{{print $2}}' | sort -u >"$out/provider-imports.txt"
"${{tc}}readelf" -p __ksymtab_strings "$out/qtn_radar_observer_f308.ko" 2>/dev/null | \
    sed -n 's/^[[:space:]]*\[[^]]*\][[:space:]]*//p' | sort -u >"$out/provider-exports.txt"

test "$(modinfo -F vermagic "$out/qtn_radar_observer_f308.ko")" = {shlex.quote(EXPECTED_VERMAGIC)}
test "$(modinfo -F depends "$out/qtn_radar_observer_f308.ko")" = ''
grep -q 'Machine:.*ARC' "$out/provider-readelf.txt"
grep -q 'OMF308RADAR loaded observer=1 backend_ready=0 fail_closed=1' "$out/provider-strings.txt"
grep -q 'classification_algorithm=NOT_IMPLEMENTED' "$out/provider-strings.txt"
grep -q 'samples_meaningful=0' "$out/provider-strings.txt"

for symbol in {' '.join(EXPECTED_API)}; do
    grep -qx "$symbol" "$out/provider-exports.txt"
done
if grep -Eq 'writel|writeb|writew|iowrite|memcpy_toio|request_irq|free_irq|schedule|timer_setup|mod_timer|qdrv_radar_detected|mark_radar' "$out/provider-imports.txt" "$out/provider-objdump.txt"; then
    echo 'F308 provider contains forbidden write, callback, IRQ or worker path' >&2
    exit 1
fi

: >"$out/provider-import-contract.txt"
while IFS= read -r symbol; do
    test -n "$symbol" || continue
    if grep -q "[[:space:]]$symbol[[:space:]]" "$kout/Module.symvers"; then
        printf '%s=EXPORTED_BY_EXACT_F301_F306_KERNEL\n' "$symbol"
    else
        printf '%s=MISSING\n' "$symbol"
        exit 1
    fi
done <"$out/provider-imports.txt" >"$out/provider-import-contract.txt"

# Link-probe current qdrv with the internal fail-closed compatibility object removed.
rm -rf "$qdrv_build"
mkdir -p "$qdrv_build/qdrv" "$qdrv_build/wlan"
cp -a "$qdrv_source/." "$qdrv_build/qdrv/"
cp "$qdrv_source/../wlan/openmitrastar_beacon_preflight.h" "$qdrv_build/wlan/"
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
case ",$(modinfo -F depends "$qdrv_build/qdrv/qdrv.ko")," in
    *,qtn_radar_observer_f308,*) ;;
    *) echo 'externalized qdrv does not depend on qtn_radar_observer_f308' >&2; exit 1 ;;
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

    provider = OUT / "qtn_radar_observer_f308.ko"
    exports = tuple(line for line in (OUT / "provider-exports.txt").read_text(encoding="ascii").splitlines() if line)
    imports = tuple(line for line in (OUT / "provider-imports.txt").read_text(encoding="ascii").splitlines() if line)
    qdrv_imports = tuple(line for line in (OUT / "qdrv-external-provider-imports.txt").read_text(encoding="ascii").splitlines() if line)
    if exports != tuple(sorted(EXPECTED_API)):
        raise SystemExit("F308 export set differs from the expected radar ABI")
    if imports != tuple(sorted(EXPECTED_PROVIDER_IMPORTS)):
        raise SystemExit(f"F308 provider import drift: {imports}")
    if not all(symbol in qdrv_imports for symbol in EXPECTED_QDRV_IMPORTS):
        raise SystemExit("externalized qdrv does not import the complete F308 ABI")

    source_paths = (
        SOURCE / "Makefile",
        SOURCE / "qtn_radar_observer_f308.c",
        ROOT / "tools/build_f308_radar_observer_offline.py",
        ROOT / "tools/test_f308_radar_observer_offline.py",
        ROOT / "docs/OPENMITRASTAR_F308_RADAR_OBSERVER.md",
    )

    manifest = {
        "schema": "openmitrastar.f308-radar-observer-offline/v1",
        "date": "2026-09-04",
        "status": "PASS",
        "classification": "OFFLINE_BOUNDED_READ_ONLY_OBSERVER_NOT_A_DETECTOR",
        "target": {
            "device": "HGW-500BNA-QCv2 A2",
            "architecture": "ARC700 little-endian",
            "kernel_release": EXPECTED_RELEASE,
            "config_sha256": EXPECTED_CONFIG_SHA256,
            "vmlinux_sha256": EXPECTED_VMLINUX_SHA256,
            "module_symvers_sha256": EXPECTED_SYMVERS_SHA256,
            "firmware_lineage": lineage,
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
        "behavior": {
            "observe_enable_default": False,
            "backend_ready": False,
            "radar_start": False,
            "radar_get_status": False,
            "dfs_rqmt_code": "DFS_RQMT_UNKNOWN",
            "registrations": "-EOPNOTSUPP and never stored",
            "callback_invocations": 0,
            "rf_register_writes": 0,
            "workers_or_timers": 0,
            "irqs": 0,
            "procfs": "/proc/openmitrastar_radar_f308/{status,snapshot}, mode 0444",
            "snapshot_max_pairs": 18,
            "samples_meaningful": False,
            "configuration_known": False,
        },
        "qdrv_link_probe": {
            "status": "PASS",
            "internal_qdrv_radar_compat_removed_in_temporary_build": True,
            "provider_dependency": "qtn_radar_observer_f308",
            "expected_import_count": len(EXPECTED_QDRV_IMPORTS),
            "not_packaged_or_loaded": True,
        },
        "source_contract": contract,
        "source_artifacts": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in source_paths
        ],
        "limits": [
            "F303 proves the OEM configures the radar block before useful acquisition.",
            "F308 performs no such configuration and therefore labels every snapshot unconfigured and non-meaningful.",
            "Manual ring windows are bounded and do not assert OEM pointer chronology.",
            "No classifier, CAC authority, radar callback or TX authorization exists.",
        ],
        "safety": {
            "firmware_generated": False,
            "integrated_into_firmware": False,
            "module_loaded": False,
            "router_contacted": False,
            "aelita_contacted": False,
            "uart": False,
            "tftp": False,
            "flash": False,
            "mtd": False,
        },
        "provenance": {
            "f302_scaffold": "work/kernel-port/modules/f302_radar_native_fail_closed/qtn_radar_native_f302.c",
            "f303_map": "docs/OPENMITRASTAR_F303_OEM_RADAR_RE.md",
            "f307_replay": "docs/OPENMITRASTAR_F307_RADAR_REPLAY.md",
            "oem_radar_sha256": EXPECTED_OEM_RADAR_SHA256,
        },
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
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
        "qdrv_link_probe": "PASS",
        "hardware_actions": 0,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
