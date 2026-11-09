#!/usr/bin/env python3
"""Build the offline F319 claim-only Topaz SPI ownership probe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-spi-owner-probe"
OUT = ROOT / "outputs/kernel-port/f319-spi-owner-probe-20260905"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f223-emac-rxring256"
MODULE_BUILD = "/home/user/openmitrastar-build/f319-spi-owner-probe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()

    source = (SOURCE / "qtn-topaz-spi-owner-probe.c").read_text(encoding="ascii")
    required = (
        "request_mem_region(TOPAZ_SPI_BASE_PHYS",
        "ioremap(TOPAZ_SPI_BASE_PHYS",
        "controller_read_count",
        "controller_write_count",
        "transaction_provider_ready",
        "of_machine_is_compatible(\"mitrastar,hgw-500bna-qcv2\")",
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f"missing F319 ownership contract: {marker}")
    forbidden = (
        "readl(",
        "readb(",
        "writel(",
        "writeb(",
        "memcpy_fromio",
        "memcpy_toio",
        "mtd_device_register",
        "SPI_WRITE_ENABLE",
        "SPI_PAGE_PROGRAM",
        "SPI_SECTOR_ERASE",
        "SPI_GBLOCK",
    )
    for marker in forbidden:
        if marker in source:
            raise SystemExit(f"forbidden controller access in F319: {marker}")

    if OUT.exists():
        if not args.replace_existing:
            raise SystemExit(f"refusing to overwrite evidence directory: {OUT}")
        if OUT.resolve().parent != (ROOT / "outputs/kernel-port").resolve():
            raise SystemExit(f"unsafe output path: {OUT}")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    source_wsl = f"{WS_ROOT}/{SOURCE.relative_to(ROOT).as_posix()}"
    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    shell = f"""
set -eu
root={shlex.quote(WS_ROOT)}
src={shlex.quote(KERNEL_SRC)}
kout={shlex.quote(KERNEL_OUT)}
mod={shlex.quote(MODULE_BUILD)}
out={shlex.quote(out_wsl)}
source_dir={shlex.quote(source_wsl)}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
rm -rf "$mod"
mkdir -p "$mod" "$out"
cp "$source_dir/qtn-topaz-spi-owner-probe.c" "$mod/"
cp "$source_dir/Makefile" "$mod/"
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" modules_prepare
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$mod" modules >"$out/module-build.log" 2>&1
cp "$mod/qtn-topaz-spi-owner-probe.ko" "$out/"
"${{tc}}readelf" -h "$out/qtn-topaz-spi-owner-probe.ko" >"$out/readelf.txt"
"${{tc}}objdump" -dr "$out/qtn-topaz-spi-owner-probe.ko" >"$out/objdump.txt"
"${{tc}}nm" -u "$out/qtn-topaz-spi-owner-probe.ko" | awk '{{print $2}}' >"$out/undefined-symbols.txt"
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
strings "$out/qtn-topaz-spi-owner-probe.ko" | grep -q 'OMSPIOWNER claim-only'
if grep -Eq '\\b(readl|readb|writel|writeb|memcpy_fromio|memcpy_toio)\\b' "$out/objdump.txt"; then
    echo 'forbidden MMIO access symbol present' >&2
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
    (OUT / "build.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (OUT / "build.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)

    module = OUT / "qtn-topaz-spi-owner-probe.ko"
    imports = [
        line.strip()
        for line in (OUT / "undefined-symbols.txt").read_text(encoding="ascii").splitlines()
        if line.strip()
    ]
    manifest = {
        "schema": "openmitrastar.f319-spi-owner-probe/v1",
        "date": "2026-09-05",
        "status": "PASS",
        "classification": "OFFLINE_CLAIM_ONLY_MODULE_NOT_LOADED",
        "artifact": {
            "file": module.name,
            "bytes": module.stat().st_size,
            "sha256": sha256(module),
            "vermagic": "5.10.260-openmitrastar-radiohw mod_unload ARC700",
        },
        "target": {
            "model": "HGW-500BNA-QCv2 A2",
            "controller_resource": "0xe4030000+0x00010000",
        },
        "contract": {
            "exact_machine_gate": True,
            "exclusive_resource_claim": True,
            "controller_mapping": True,
            "mmio_reads": 0,
            "mmio_writes": 0,
            "spi_opcodes": 0,
            "mtd_registration": False,
            "transaction_provider_ready": False,
            "autoload": False,
        },
        "kernel_contract": {
            "undefined_symbols": imports,
            "all_imports_exported": True,
        },
        "hardware_actions": {
            "router": False,
            "uart": False,
            "module_load": False,
            "flash": False,
            "mtd": False,
        },
        "physical_validation": "NOT_RUN",
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
