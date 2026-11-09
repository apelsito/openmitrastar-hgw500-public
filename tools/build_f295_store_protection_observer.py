#!/usr/bin/env python3
"""Build the F295 read-command-only SPI protection observer for ARC700."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-store-protection-observer"
OUT = ROOT / "outputs/kernel-port/f295-store-protection-observer-20260904"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f293-emac-hw-rx-demand"
MODULE_BUILD = "/home/user/openmitrastar-build/f295-store-protection-observer"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    source = (SOURCE / "qtn-topaz-store-protection-observer.c").read_text(encoding="utf-8")
    required = (
        "LYOKO_STORE_OFFSET\t0x00dc0000",
        "LYOKO_STORE_SIZE\t0x001c0000",
        "LYOKO_STORE_ERASE_SIZE\t0x00010000",
        "TOPAZ_SPI_EXPECTED_ID\t0x00c22018",
        "SPI_READ_SCUR",
        "SPI_READ_DPB",
        "store_dpb_scan_count",
        "read_commands_only = true",
        "OMSTOREPROBE read-only=1",
    )
    forbidden = (
        "SPI_WRITE_ENABLE",
        "SPI_WRITE_DISABLE",
        "SPI_PAGE_PROGRAM",
        "SPI_SECTOR_ERASE",
        "SPI_WRITE_DPB",
        "SPI_GBLOCK",
        "mtd_device_register",
        "mtd_device_unregister",
        "memcpy_toio",
        "writeb(",
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f"missing protection-observer contract: {marker}")
    for marker in forbidden:
        if marker in source:
            raise SystemExit(f"forbidden flash mutation primitive: {marker}")
    if source.count("qtn_spi_read_command(ctrl,") != 2:
        raise SystemExit("observer must expose exactly the SCUR and DPB read-command call sites")

    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable evidence directory: {OUT}")
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
cp "$root/work/kernel-port/modules/qtn-topaz-store-protection-observer/qtn-topaz-store-protection-observer.c" "$mod/"
cp "$root/work/kernel-port/modules/qtn-topaz-store-protection-observer/Makefile" "$mod/"
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" modules_prepare
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$mod" modules >"$out/module-build.log" 2>&1
cp "$mod/qtn-topaz-store-protection-observer.ko" "$out/"
"${{tc}}readelf" -h "$out/qtn-topaz-store-protection-observer.ko" >"$out/readelf.txt"
"${{tc}}objdump" -dr "$out/qtn-topaz-store-protection-observer.ko" >"$out/objdump.txt"
"${{tc}}nm" -u "$out/qtn-topaz-store-protection-observer.ko" | awk '{{print $2}}' >"$out/undefined-symbols.txt"
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
strings "$out/qtn-topaz-store-protection-observer.ko" | grep -q 'OMSTOREPROBE read-only=1'
strings "$out/qtn-topaz-store-protection-observer.ko" | grep -q 'vermagic=5.10.260-openmitrastar-radiohw mod_unload ARC700'
if grep -Eq 'mtd_device_(parse_)?register|mtd_device_unregister|memcpy_toio' "$out/undefined-symbols.txt"; then
  echo 'forbidden write-capable import present' >&2
  exit 1
fi
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

    module = OUT / "qtn-topaz-store-protection-observer.ko"
    imports = [line.strip() for line in (OUT / "undefined-symbols.txt").read_text(encoding="ascii").splitlines() if line.strip()]
    manifest = {
        "schema": "openmitrastar.f295-store-protection-observer/v1",
        "classification": "OFFLINE_READ_COMMAND_ONLY_MODULE_NEVER_LOADED",
        "status": "PASS",
        "artifact": {"file": module.name, "bytes": module.stat().st_size, "sha256": sha256(module)},
        "target": {
            "model": "HGW-500BNA-QCv2",
            "kernel": "5.10.260-openmitrastar-radiohw",
            "architecture": "ARC700 little-endian",
            "expected_flash": "MX25L12836E",
            "expected_jedec_id": "0xc22018",
            "store": {"physical_offset": "0xdc0000", "bytes": 0x1C0000, "erase_size": 0x10000, "eraseblocks": 28},
        },
        "observes": [
            "jedec_id",
            "status_register",
            "security_register",
            "raw_dpb_first_last",
            "raw_dpb_zero_nonzero_counts",
            "spi_control_restore",
        ],
        "safety": {
            "read_commands_only": True,
            "mtd_registration": False,
            "flash_window_mapping": False,
            "program": False,
            "erase": False,
            "write_enable": False,
            "protection_mutation": False,
            "module_autoload": False,
        },
        "kernel_contract": {
            "vermagic": "5.10.260-openmitrastar-radiohw mod_unload ARC700",
            "undefined_symbols": imports,
            "all_imports_exported_by_f293_vmlinux": True,
        },
        "hardware_actions": {"router": False, "uart": False, "module_load": False, "mtd_write": False},
        "physical_validation": "NOT_RUN",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "SHA256SUMS"),
        encoding="ascii",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
