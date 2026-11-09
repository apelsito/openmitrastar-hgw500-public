#!/usr/bin/env python3
"""Build the F216 no-MMIO MTD-core observer for ARC700 Linux 5.10."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-mtd-observer"
OUT = ROOT / "outputs/kernel-port/f216-mtd-core-observer-20260901"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f180-storage-readonly-probe"
MODULE_BUILD = "/home/user/openmitrastar-build/f216-mtd-core-observer-module"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
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
cp "$root/work/kernel-port/modules/qtn-topaz-mtd-observer/qtn-topaz-mtd-observer.c" "$mod/"
cp "$root/work/kernel-port/modules/qtn-topaz-mtd-observer/Makefile" "$mod/"
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" modules_prepare
make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$mod" modules >"$out/module-build.log" 2>&1
cp "$mod/qtn-topaz-mtd-observer.ko" "$out/"
"${{tc}}readelf" -h "$out/qtn-topaz-mtd-observer.ko" >"$out/readelf.txt"
"${{tc}}objdump" -dr "$out/qtn-topaz-mtd-observer.ko" >"$out/objdump.txt"
grep -q 'ARC700, v4 ABI' "$out/readelf.txt"
strings "$out/qtn-topaz-mtd-observer.ko" | grep -q 'OMMTDOBS'
if grep -Eq '\b(ioremap|readl|writel)\b' "$out/objdump.txt"; then
  echo 'forbidden direct MMIO symbol present' >&2
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

    module = OUT / "qtn-topaz-mtd-observer.ko"
    manifest = {
        "schema": "openmitrastar.f216-mtd-core-observer/v1",
        "classification": "OFFLINE_MODULE_NOT_LOADED",
        "artifact": {"file": module.name, "bytes": module.stat().st_size, "sha256": sha256(module)},
        "target": {"model": "HGW-500BNA-QCv2", "mtd_name": "lyoko_store"},
        "capabilities": {
            "mtd_core_lookup": True,
            "reports_geometry": True,
            "direct_mmio": False,
            "read_data": False,
            "erase": False,
            "write": False,
            "mtd_registration": False,
        },
        "supersedes": {
            "artifact": "f181-spi-readonly-probe",
            "reason": "physical F214 Machine Check at direct MMIO read 0xe4039f00",
        },
        "hardware_actions": {"router": False, "uart": False, "module_load": False, "mtd": False},
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
