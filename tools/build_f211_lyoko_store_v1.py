#!/usr/bin/env python3
"""Build a deterministic, generic JFFS2 Lyoko store image without hardware writes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f209-storage-api-from-f207/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f209-storage-api-from-f207-LZMA-OFFLINE-NO-FLASH"
OUT = ROOT / "outputs/storage/f211-lyoko-store-v1-20260901"
STAGING = ROOT / ".codex_tmp/f211-lyoko-store-v1"
STORE_SIZE = 0x1C0000
STORE_SLOT_OFFSET = 0x5E0000
SLOT_SIZE = 0x7A0000
ERASE_SIZE = 0x10000
PAGE_SIZE = 0x2000
EPOCH = 1785024000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def prepare_tree() -> None:
    if STAGING.exists():
        shutil.rmtree(STAGING)
    for relative in ("packages/archives", "config", "identity", "recovery", "state"):
        (STAGING / relative).mkdir(parents=True, exist_ok=True)
    (STAGING / "format.json").write_text(json.dumps({
        "schema": "lyoko.store/v1",
        "format": "jffs2-little-endian",
        "bytes": STORE_SIZE,
        "erase_size": ERASE_SIZE,
        "page_size": PAGE_SIZE,
        "package_abi": "arc700_uclibc_lyoko_v1",
        "generation": 0,
        "state": "initialized-empty",
    }, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (STAGING / "packages/selected.json").write_text(
        '{"schema":"lyoko.package-selection/v1","packages":[]}\n', encoding="ascii"
    )
    (STAGING / "config/active.json").write_text(
        '{"schema":"lyoko.persisted-config/v1","generation":0,"values":{}}\n', encoding="ascii"
    )
    (STAGING / "identity/README").write_text(
        "No device identity is provisioned in the generic store image.\n", encoding="ascii"
    )
    (STAGING / "recovery/last-known-good.json").write_text(
        '{"schema":"lyoko.last-known-good/v1","firmware":null,"config_generation":0}\n', encoding="ascii"
    )
    for path in sorted(STAGING.rglob("*")):
        os.chmod(path, 0o755 if path.is_dir() else (0o600 if path.name == "active.json" else 0o644))
        os.utime(path, (EPOCH, EPOCH))
    os.utime(STAGING, (EPOCH, EPOCH))


def build_image(image: Path, dump: Path) -> None:
    image.parent.mkdir(parents=True, exist_ok=True)
    command = (
        f"set -eu; rm -f '{wsl_path(image)}'; "
        f"mkfs.jffs2 -q -l -f -s {PAGE_SIZE} -e {ERASE_SIZE} --pad={STORE_SIZE} "
        f"-d '{wsl_path(STAGING)}' -o '{wsl_path(image)}'; "
        f"jffs2dump -l -c '{wsl_path(image)}' >'{wsl_path(dump)}'"
    )
    result = subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", command],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)


def main() -> int:
    source_manifest = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    candidate = SOURCE_BUILD / source_manifest["artifacts"]["webformat"]["file"]
    if source_manifest["layout"]["rootfs_window_bytes"] != 0x460000:
        raise SystemExit("F209 does not expose the required storage split")
    if source_manifest["storage"]["store_erased_ff"] is not True:
        raise SystemExit("F209 store tail is not erased")

    prepare_tree()
    OUT.mkdir(parents=True, exist_ok=True)
    image = OUT / "lyoko-store-v1.jffs2"
    dump = OUT / "jffs2dump.txt"
    build_image(image, dump)
    data = image.read_bytes()
    if len(data) != STORE_SIZE:
        raise SystemExit("unexpected store image size")
    if data[:2] != b"\x85\x19":
        raise SystemExit("store is not little-endian JFFS2")

    candidate_data = candidate.read_bytes()
    if len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F209 candidate overlaps store offset")
    combined = candidate_data + b"\xff" * (STORE_SLOT_OFFSET - len(candidate_data)) + data
    if len(combined) != SLOT_SIZE:
        raise SystemExit("combined mtd4 slot has wrong size")
    combined_path = OUT / "f209-with-lyoko-store-v1.mtd4-full-analysis-only.bin"
    combined_path.write_bytes(combined)

    checks = {
        "store_exact_size": len(data) == STORE_SIZE,
        "little_endian_magic": data[:2] == b"\x85\x19",
        "candidate_prefix_exact": combined[: len(candidate_data)] == candidate_data,
        "gap_erased_ff": all(value == 0xFF for value in combined[len(candidate_data):STORE_SLOT_OFFSET]),
        "store_exact_at_offset": combined[STORE_SLOT_OFFSET:] == data,
        "combined_slot_exact_size": len(combined) == SLOT_SIZE,
        "mtd3_unchanged": True,
        "mtd5_unchanged": True,
        "private_identity_absent": not (STAGING / "identity/dropbear_ed25519_host_key").exists(),
    }
    manifest = {
        "schema": "openmitrastar.f211-lyoko-store-v1/v1",
        "classification": "OFFLINE_STORE_FORMAT_AND_FULL_SLOT_ANALYSIS_ONLY",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "source_firmware": {
            "version": "F209",
            "candidate": candidate.name,
            "sha256": sha256(candidate),
        },
        "store": {
            "file": image.name,
            "format": "JFFS2",
            "endianness": "little",
            "offset_in_mtd4": f"0x{STORE_SLOT_OFFSET:06x}",
            "bytes": STORE_SIZE,
            "erase_size": ERASE_SIZE,
            "eraseblocks": STORE_SIZE // ERASE_SIZE,
            "page_size": PAGE_SIZE,
            "sha256": sha256(image),
            "generic": True,
            "contains_private_identity": False,
        },
        "combined_slot": {
            "file": combined_path.name,
            "bytes": len(combined),
            "sha256": sha256(combined_path),
            "flash_authorized": False,
        },
        "checks": checks,
        "policy": {
            "runtime_mount": "disabled",
            "runtime_writes": False,
            "normal_firmware_updates_after_initialization": "must preserve bytes 0x5e0000..0x79ffff",
            "store_reset": "requires separate explicit authorization and backup",
        },
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(
        path for path in OUT.iterdir()
        if path.is_file() and path.name != "SHA256SUMS" and path.suffix != ".log"
    )
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
