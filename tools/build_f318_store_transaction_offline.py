#!/usr/bin/env python3
"""Build and audit the portable F318 two-eraseblock store transaction core."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f318_store_transaction"
OUT = ROOT / "outputs/kernel-port/f318-store-transaction-core-20260905"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
TOOLCHAIN = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"


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
        timeout=300,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()

    source = (SOURCE / "f318_store_transaction.c").read_text(encoding="ascii")
    header = (SOURCE / "f318_store_transaction.h").read_text(encoding="ascii")
    required = (
        "F318_STORE_SLOT_COUNT 2u",
        "F318_STORE_OFFSET 0x00dc0000u",
        "F318_STORE_PAYLOAD_MAX 256u",
        "protection_restore_attempted",
        "witnesses_unchanged",
        "f318_store_write_slot",
    )
    for marker in required:
        if marker not in source and marker not in header:
            raise SystemExit(f"missing F318 bounded transaction contract: {marker}")
    forbidden = (
        "GBLOCK",
        "GANG_BLOCK",
        "TOPAZ_SPI_BASE_PHYS",
        "ioremap",
        "mtd_device_register",
        "SPI_SECTOR_ERASE",
        "SPI_PAGE_PROGRAM",
        "mtd5",
    )
    for marker in forbidden:
        if marker in source or marker in header:
            raise SystemExit(f"forbidden hardware/global primitive in portable core: {marker}")

    if OUT.exists():
        if not args.replace_existing:
            raise SystemExit(f"refusing to overwrite evidence directory: {OUT}")
        if OUT.resolve().parent != (ROOT / "outputs/kernel-port").resolve():
            raise SystemExit(f"unsafe output path: {OUT}")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    source_wsl = f"{WS_ROOT}/{SOURCE.relative_to(ROOT).as_posix()}"
    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    script = f"""
set -eu
src={shlex.quote(source_wsl)}
out={shlex.quote(out_wsl)}
tc={shlex.quote(TOOLCHAIN)}
make -C "$src" clean test >"$out/host-tests.log" 2>&1
make -C "$src" analyze >"$out/analyzer.log" 2>&1
make -C "$src" clean >>"$out/host-tests.log" 2>&1
mkdir -p /tmp/f318-a /tmp/f318-b
"${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -ffunction-sections -fdata-sections -I"$src" -c "$src/f318_store_transaction.c" -o /tmp/f318-a/f318_store_transaction.o
"${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -ffunction-sections -fdata-sections -I"$src" -c "$src/f318_store_transaction.c" -o /tmp/f318-b/f318_store_transaction.o
cmp /tmp/f318-a/f318_store_transaction.o /tmp/f318-b/f318_store_transaction.o
"${{tc}}ar" rcsD /tmp/f318-a/libf318store.a /tmp/f318-a/f318_store_transaction.o
"${{tc}}ar" rcsD /tmp/f318-b/libf318store.a /tmp/f318-b/f318_store_transaction.o
cmp /tmp/f318-a/libf318store.a /tmp/f318-b/libf318store.a
cp /tmp/f318-a/libf318store.a "$out/libf318store.a"
"${{tc}}nm" -u "$out/libf318store.a" >"$out/undefined.txt"
"${{tc}}size" "$out/libf318store.a" >"$out/size.txt"
"${{tc}}readelf" -h /tmp/f318-a/f318_store_transaction.o >"$out/readelf.txt"
grep -q 'Machine:.*ARCompact' "$out/readelf.txt"
"""
    result = run_wsl(script)
    (OUT / "build.stdout.log").write_text(result.stdout, encoding="utf-8")
    (OUT / "build.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)

    artifact = OUT / "libf318store.a"
    sources = sorted(
        path
        for path in SOURCE.iterdir()
        if path.is_file() and (path.name == "Makefile" or path.suffix in {".c", ".h"})
    )
    manifest = {
        "schema": "openmitrastar.f318-store-transaction-core/v1",
        "date": "2026-09-05",
        "status": "PASS",
        "classification": "PORTABLE_OFFLINE_TWO_ERASEBLOCK_TRANSACTION_CORE",
        "artifact": {
            "file": artifact.name,
            "bytes": artifact.stat().st_size,
            "sha256": sha256(artifact),
            "reproducible_two_builds": True,
        },
        "store": {
            "physical_offset": "0x00dc0000",
            "erase_bytes": 0x10000,
            "slot_count": 2,
            "slot_offsets": ["0x00dc0000", "0x00dd0000"],
            "payload_max_bytes": 256,
            "remaining_store_blocks_untouched": 26,
        },
        "transaction": {
            "power_loss_commit_marker": True,
            "payload_crc32": True,
            "exact_readback": True,
            "exclusive_owner_required": True,
            "target_protection_snapshot": True,
            "exact_target_protection_restore": True,
            "cross_partition_protection_witnesses": True,
            "global_protection_operation_available": False,
        },
        "provider_boundary": {
            "mmio_access": False,
            "mtd_registration": False,
            "spi_opcode_emission": False,
            "hardware_provider": "NOT_IMPLEMENTED",
            "physical_validation": "NOT_RUN",
        },
        "authority": {
            "persistent_writes_enabled": False,
            "firmware_candidate_produced": False,
            "flash_supported": False,
        },
        "sources": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sources
        ],
        "hardware_actions": {
            "router": False,
            "uart": False,
            "ssh_mutation": False,
            "flash": False,
            "mtd": False,
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files),
        encoding="ascii",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
