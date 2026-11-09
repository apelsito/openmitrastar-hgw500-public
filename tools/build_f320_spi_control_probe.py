#!/usr/bin/env python3
"""Offline only: F320 single control read, provenance, host tests and ARC ABI."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-spi-control-probe"
NAME = "qtn-topaz-spi-control-probe"
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f319-device-bound"
BASE = "openmitrastar-linux510-f319-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
EXPECTED_F319 = "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9"
EXPECTED_CONFIG = "cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e"
KERNEL = "/home/user/mitrastar-linux-5.10.260"
KOUT = "/home/user/openmitrastar-build/f223-emac-rxring256"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl(path: Path) -> str:
    path = path.resolve()
    return f"/mnt/{path.drive[0].lower()}/{path.as_posix()[3:]}"


def check_source(text: str) -> None:
    # Require the exact intended two read call sites, no writable interface or loop.
    calls = re.findall(r"\breadl\s*\(", text)
    if len(calls) != 2:
        raise ValueError("F320 requires exactly two MMIO call sites: map and SPI control")
    for token in ("writel(", "writeb(", "writew(", "memcpy_toio", "memcpy_fromio",
                  "mtd_device_register", "0xe4030000", "0x9f00", "0x0500", "0xe000u",
                  "while (", "for (", "schedule_work", "module_param_cb"):
        if token in text:
            raise ValueError(f"forbidden F320 operation: {token}")
    for token in ("#define TOPAZ_SYSCTL_MAP_REGISTER 0xe0000004u",
                  "#define TOPAZ_SPI_BASE_PHYS 0xe2000000u",
                  "#define TOPAZ_SPI_CONTROL 0x0004u", "#define TOPAZ_MAP_BITS 0x60000000u",
                  "if (!execute_read)", "if (map_register_value & TOPAZ_MAP_BITS)",
                  'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
                  "controller_value = read_control_once(controller_mapping + TOPAZ_SPI_CONTROL);"):
        if token not in text:
            raise ValueError(f"missing F320 constraint: {token}")
    if text.index("if (map_register_value & TOPAZ_MAP_BITS)") > text.index("controller_value = read_control_once"):
        raise ValueError("map check must precede SPI read")


def check_read_helpers(disassembly: str) -> None:
    for function in ("read_map_once", "read_control_once"):
        match = re.search(r"^[0-9a-f]+ <" + function + r">:\n(.*?)(?=\n[0-9a-f]+ <|\nDisassembly|\Z)",
                          disassembly, re.M | re.S)
        if not match:
            raise ValueError(f"missing dedicated read helper: {function}")
        body = match.group(1)
        if len(re.findall(r"\bld(?:\.di)?\s", body)) != 1:
            raise ValueError(f"helper must have one 32-bit load: {function}")
        if re.search(r"\b(?:st\w*|jl\w*|bl\w*|loop\w*|b\w*)\s", body):
            raise ValueError(f"helper has store/call/loop/branch: {function}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        raise SystemExit("refusing to replace F320 evidence")
    if not out.is_relative_to((ROOT / "outputs/kernel-port").resolve()):
        raise SystemExit("F320 outputs must be under outputs/kernel-port")
    check_source((SOURCE / f"{NAME}.c").read_text(encoding="ascii"))
    if sha(DEVICE / f"{BASE}.webformat.bin") != EXPECTED_F319:
        raise SystemExit("F319 base hash mismatch")
    if sha(DEVICE / f"{BASE}.config") != EXPECTED_CONFIG:
        raise SystemExit("F319 config mismatch")
    out.mkdir(parents=True, exist_ok=False)
    # Each compilation gets a brand-new private build directory. Never replace F319.
    script = f"""set -eu
export LC_ALL=C
src={shlex.quote(KERNEL)}
kout={shlex.quote(KOUT)}
source_dir={shlex.quote(wsl(SOURCE))}
out={shlex.quote(wsl(out))}
base={shlex.quote(wsl(DEVICE / BASE))}
tc={shlex.quote(wsl(ROOT / 'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-'))}
test "$(sha256sum "$kout/.config" | cut -d ' ' -f1)" = {EXPECTED_CONFIG}
test -s "$kout/include/generated/autoconf.h"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -fanalyzer "$source_dir/test_f320_control_probe.c" -o "$out/host-test"
"$out/host-test" > "$out/host-tests.log"
for pass in first second; do
    mod="$out/build-$pass"
    mkdir "$mod"
    cp "$source_dir/{NAME}.c" "$source_dir/Makefile" "$mod/"
    make -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$mod" modules > "$out/build-$pass.log" 2>&1
done
cmp "$out/build-first/{NAME}.ko" "$out/build-second/{NAME}.ko"
cp "$out/build-first/{NAME}.ko" "$out/{NAME}.ko"
"${{tc}}readelf" -h "$out/{NAME}.ko" > "$out/readelf.txt"
"${{tc}}objdump" -dr "$out/{NAME}.ko" > "$out/objdump.txt"
"${{tc}}nm" -u "$out/{NAME}.ko" | awk '{{print $2}}' > "$out/undefined-symbols.txt"
"${{tc}}nm" "$base.vmlinux" > "$out/f319-kernel-symbols.txt"
dtc -I dtb -O dts "$base.dtb" > "$out/f319-device-tree.dts" 2> "$out/dtc.stderr.log"
cp "$src/arch/arc/mm/ioremap.c" "$out/kernel-ioremap.c"
cp "$src/arch/arc/kernel/traps.c" "$out/kernel-traps.c"
cp "$src/arch/arc/include/asm/io.h" "$out/kernel-io.h"
"""
    proc = subprocess.run(["wsl.exe", "-d", args.distro, "-u", "root", "-e", "bash",
                           "--noprofile", "--norc", "-c", script], capture_output=True,
                          text=True, timeout=300, cwd=ROOT)
    (out / "build.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "build.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise SystemExit(f"F320 build failed; evidence={out}\n{proc.stderr}")
    objdump = (out / "objdump.txt").read_text(encoding="ascii")
    check_read_helpers(objdump)
    symbols = (out / "f319-kernel-symbols.txt").read_text(encoding="ascii")
    imports = (out / "undefined-symbols.txt").read_text(encoding="ascii").split()
    if any(not re.search(r"\b__ksymtab_" + re.escape(item) + r"$", symbols, re.M) for item in imports):
        raise SystemExit("F320 import missing from exact F319 vmlinux")
    if "ARC700, v4 ABI" not in (out / "readelf.txt").read_text():
        raise SystemExit("unexpected ARC ABI")
    dts = (out / "f319-device-tree.dts").read_text()
    for marker in ("interrupt-controller@e0000000", "serial@f0000000", "ethernet@e8000000"):
        if marker not in dts:
            raise SystemExit("F319 DTB no longer matches legacy platform map")
    provenance = [SOURCE / f"{NAME}.c", SOURCE / "Makefile", SOURCE / "test_f320_shim.h",
                  SOURCE / "test_f320_control_probe.c", Path(__file__).resolve(),
                  ROOT / "work/sources/Quantenna-GPL/common/topaz_config.h",
                  ROOT / "work/sources/Quantenna-GPL/common/ruby_platform.h",
                  ROOT / "work/sources/Quantenna-GPL/common/topaz_platform.h",
                  ROOT / "work/sources/Quantenna-GPL/drivers/ruby/spi_api.c",
                  ROOT / "outputs/kernel-port/f295-store-protection-observer-20260904/objdump.txt",
                  ROOT / "outputs/preflight/f310-store-protection-probe-20260904T211740Z/uart/uart.log",
                  DEVICE / f"{BASE}.dtb", DEVICE / f"{BASE}.vmlinux", DEVICE / f"{BASE}.config"]
    module = out / f"{NAME}.ko"
    manifest = {
        "schema": "openmitrastar.f320-spi-control-probe/v1", "status": "OFFLINE_PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact": {"file": module.name, "bytes": module.stat().st_size, "sha256": sha(module)},
        "source_f319_sha256": EXPECTED_F319,
        "contract": {"spi_address": "0xe2000004", "spi_reads_max": 1,
                     "sysctl_map_address": "0xe0000004", "sysctl_reads_max": 1,
                     "required_map_bits": "(value & 0x60000000) == 0",
                     "mmio_writes": 0, "flash_opcodes": 0, "mtd_registration": False,
                     "autoload": False, "default_access": "REFUSED", "provider_ready": False,
                     "resource_claim_scope": "Linux resource users only; not hardware arbitration"},
        "validation": {"host_cases": 9, "host_analyzer": "PASS", "two_builds_identical": True,
                       "arc_helpers_one_load_each": True, "imports_exported_by_exact_f319": imports},
        "physical_validation": "NOT_RUN", "flash_supported": False, "release_eligible": False,
        "hardware_actions": {"router": False, "uart": False, "flash": False, "module_load": False},
        "risk": "Map-bit check is also an MMIO read. A bus Machine Check can halt this kernel; neither a timeout nor exception-table fixup is a recovery guarantee.",
        "next_gate": "Reviewed versioned image and explicit physical authorization, fresh binding/lease, UART brackets and physical power-cycle contingency; F319 ACK is not reused.",
        "provenance": [{"path": str(path), "sha256": sha(path)} for path in provenance],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    (out / "SHA256SUMS").write_text("".join(f"{sha(path)}  {path.name}\n" for path in sorted(out.iterdir())
                                             if path.is_file() and path.name != "SHA256SUMS"), encoding="ascii")
    print(json.dumps({"status": manifest["status"], "manifest": str(out / "manifest.json"),
                      "artifact": manifest["artifact"], "hardware_actions": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
