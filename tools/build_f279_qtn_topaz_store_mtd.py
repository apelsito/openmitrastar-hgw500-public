#!/usr/bin/env python3
"""Build the offline F279 bounded Topaz lyoko_store MTD module."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-store-mtd"
OUT = ROOT / "outputs/kernel-port/f279-qtn-topaz-store-mtd-20260903"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f223-emac-rxring256"
MODULE_BUILD = "/home/user/openmitrastar-build/f279-qtn-topaz-store-mtd"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    source = (SOURCE / "qtn-topaz-store-mtd.c").read_text(encoding="utf-8")
    required = (
        "LYOKO_STORE_OFFSET\t0x00dc0000",
        "LYOKO_STORE_SIZE\t0x001c0000",
        "LYOKO_STORE_ERASE_SIZE\t0x00010000",
        "TOPAZ_SPI_EXPECTED_ID\t0x00c22018",
        "module_param(allow_write, bool, 0400)",
        "mtd_device_register(&store->mtd, NULL, 0)",
        "qtn_store_range_valid",
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f"missing bounded-store contract: {marker}")
    for forbidden in ("SPI_BULK_ERASE", "TOPAZ_FLASH_SIZE -", "mtd_add_partition"):
        if forbidden in source:
            raise SystemExit(f"forbidden broad flash primitive: {forbidden}")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shell = f"""
set -eu
root={shlex.quote(WS_ROOT)}
src={shlex.quote(KERNEL_SRC)}
kout={shlex.quote(KERNEL_OUT)}
mod={shlex.quote(MODULE_BUILD)}
out={shlex.quote(WS_ROOT + '/' + OUT.relative_to(ROOT).as_posix())}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
rm -rf "$mod"
mkdir -p "$mod" "$out"
cp "$root/work/kernel-port/modules/qtn-topaz-store-mtd/qtn-topaz-store-mtd.c" "$mod/"
cp "$root/work/kernel-port/modules/qtn-topaz-store-mtd/Makefile" "$mod/"
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" modules_prepare
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$mod" modules >"$out/module-build.log" 2>&1
cp "$mod/qtn-topaz-store-mtd.ko" "$out/"
"${{tc}}readelf" -h "$out/qtn-topaz-store-mtd.ko" >"$out/readelf.txt"
"${{tc}}objdump" -dr "$out/qtn-topaz-store-mtd.ko" >"$out/objdump.txt"
"${{tc}}nm" -u "$out/qtn-topaz-store-mtd.ko" | awk '{{print $2}}' >"$out/undefined-symbols.txt"
"${{tc}}nm" "$kout/vmlinux" >"$out/vmlinux-symbols.tmp"
missing=0
while IFS= read -r symbol; do
    [ -n "$symbol" ] || continue
    if grep -q "__ksymtab_${{symbol}}$" "$out/vmlinux-symbols.tmp"; then
        printf '%s=EXPORTED\n' "$symbol"
    else
        printf '%s=MISSING\n' "$symbol"
        missing=1
    fi
done <"$out/undefined-symbols.txt" >"$out/exported-symbol-contract.txt"
rm -f "$out/vmlinux-symbols.tmp"
test "$missing" -eq 0
grep -q 'ARC700, v4 ABI' "$out/readelf.txt"
strings "$out/qtn-topaz-store-mtd.ko" | grep -q 'OMSTOREMTD registered'
strings "$out/qtn-topaz-store-mtd.ko" | grep -q 'vermagic=5.10.260-openmitrastar-radiohw mod_unload ARC700'
"""
    proc = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", shell],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=900,
        check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)
    module = OUT / "qtn-topaz-store-mtd.ko"
    imports = [line.strip() for line in (OUT / "undefined-symbols.txt").read_text(encoding="ascii").splitlines() if line.strip()]
    manifest = {
        "schema": "openmitrastar.f279-qtn-topaz-store-mtd/v1",
        "classification": "OFFLINE_MODULE_NEVER_LOADED",
        "status": "PASS",
        "artifact": {"file": module.name, "bytes": module.stat().st_size, "sha256": sha256(module)},
        "target": {
            "model": "HGW-500BNA-QCv2",
            "kernel": "5.10.260-openmitrastar-radiohw",
            "architecture": "ARC700 little-endian",
            "expected_flash": "MX25L12836E",
            "expected_jedec_id": "0xc22018",
            "physical_mtd4": {"offset": "0x7e0000", "bytes": 0x7A0000},
            "store": {"offset_in_mtd4": "0x5e0000", "physical_offset": "0xdc0000", "bytes": 0x1C0000, "erase_size": 0x10000},
        },
        "safety": {
            "write_default": False,
            "register_mtd_default": False,
            "module_autoload": False,
            "bulk_erase": False,
            "registered_mtd_name": "lyoko_store_rw",
            "address_range_enforced": True,
            "mtd0_mtd1_mtd2_mtd3_mtd5_unaddressable": True,
        },
        "read_only_probe": {
            "jedec_id": True,
            "status_register": True,
            "security_register": True,
            "store_first_dpb": True,
            "store_last_dpb": True,
        },
        "kernel_contract": {
            "vermagic": "5.10.260-openmitrastar-radiohw mod_unload ARC700",
            "undefined_symbols": imports,
            "all_imports_exported_by_f223_vmlinux": True,
            "module_symvers_required": False,
        },
        "hardware_actions": {"router": False, "uart": False, "module_load": False, "mtd_write": False},
        "physical_validation": "NOT_RUN",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
