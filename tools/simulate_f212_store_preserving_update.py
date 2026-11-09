#!/usr/bin/env python3
"""Simulate a real-layout mtd4 prefix update while preserving Lyoko store."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DUMPS = ROOT / "hgw500bna-qcv2-firmware-dump-verified"
F207_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f207-storage-readonly-probe-from-f205/build"
F207_BASE = "openmitrastar-linux510-q3-persistent-f207-storage-readonly-probe-from-f205-LZMA-OFFLINE-NO-FLASH"
F209_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f209-storage-api-from-f207/build"
F209_BASE = "openmitrastar-linux510-q3-persistent-f209-storage-api-from-f207-LZMA-OFFLINE-NO-FLASH"
STORE = ROOT / "outputs/storage/f211-lyoko-store-v1-20260901/lyoko-store-v1.jffs2"
OUT = ROOT / "outputs/storage/f212-store-preserving-update-20260901"

FLASH_SIZE = 0x1000000
ERASE_SIZE = 0x10000
MTD3_OFFSET = 0x040000
MTD3_SIZE = 0x7A0000
MTD4_OFFSET = 0x7E0000
MTD4_SIZE = 0x7A0000
PREFIX_SIZE = 0x5E0000
STORE_OFFSET = MTD4_OFFSET + PREFIX_SIZE
STORE_SIZE = 0x1C0000
MTD5_OFFSET = 0xF80000
MTD5_SIZE = 0x080000


def sha(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def physical_flash() -> bytearray:
    parts = [(index, (DUMPS / f"hgw500_mtdblock{index}.bin").read_bytes()) for index in range(6)]
    flash = bytearray().join(data for _, data in parts)
    if len(flash) != FLASH_SIZE:
        raise ValueError("verified physical partitions do not total 16 MiB")
    return bytearray(flash)


def main() -> int:
    old_candidate = (F207_BUILD / f"{F207_BASE}.webformat.bin").read_bytes()
    new_candidate = (F209_BUILD / f"{F209_BASE}.webformat.bin").read_bytes()
    store = STORE.read_bytes()
    if len(store) != STORE_SIZE:
        raise SystemExit("F211 store size mismatch")
    if len(old_candidate) > PREFIX_SIZE or len(new_candidate) > PREFIX_SIZE:
        raise SystemExit("storage-aware firmware exceeds writable prefix")

    flash = physical_flash()
    initial_mtd4 = old_candidate + b"\xff" * (PREFIX_SIZE - len(old_candidate)) + store
    flash[MTD4_OFFSET:MTD4_OFFSET + MTD4_SIZE] = initial_mtd4
    before = {
        "mtd0_mtd1_mtd2": sha(flash[:MTD3_OFFSET]),
        "mtd3": sha(flash[MTD3_OFFSET:MTD3_OFFSET + MTD3_SIZE]),
        "mtd4_prefix": sha(flash[MTD4_OFFSET:MTD4_OFFSET + PREFIX_SIZE]),
        "lyoko_store": sha(flash[STORE_OFFSET:STORE_OFFSET + STORE_SIZE]),
        "mtd5": sha(flash[MTD5_OFFSET:MTD5_OFFSET + MTD5_SIZE]),
    }

    flash[MTD4_OFFSET:MTD4_OFFSET + PREFIX_SIZE] = b"\xff" * PREFIX_SIZE
    flash[MTD4_OFFSET:MTD4_OFFSET + len(new_candidate)] = new_candidate
    after = {
        "mtd0_mtd1_mtd2": sha(flash[:MTD3_OFFSET]),
        "mtd3": sha(flash[MTD3_OFFSET:MTD3_OFFSET + MTD3_SIZE]),
        "mtd4_prefix": sha(flash[MTD4_OFFSET:MTD4_OFFSET + PREFIX_SIZE]),
        "lyoko_store": sha(flash[STORE_OFFSET:STORE_OFFSET + STORE_SIZE]),
        "mtd5": sha(flash[MTD5_OFFSET:MTD5_OFFSET + MTD5_SIZE]),
    }
    checks = {
        "prefix_changed": before["mtd4_prefix"] != after["mtd4_prefix"],
        "new_candidate_exact": flash[MTD4_OFFSET:MTD4_OFFSET + len(new_candidate)] == new_candidate,
        "unused_prefix_erased": all(value == 0xFF for value in flash[MTD4_OFFSET + len(new_candidate):STORE_OFFSET]),
        "store_preserved": before["lyoko_store"] == after["lyoko_store"] == sha(store),
        "mtd3_preserved": before["mtd3"] == after["mtd3"],
        "mtd5_preserved": before["mtd5"] == after["mtd5"],
        "bootloader_and_env_preserved": before["mtd0_mtd1_mtd2"] == after["mtd0_mtd1_mtd2"],
    }
    result = {
        "schema": "openmitrastar.f212-store-preserving-update/v1",
        "classification": "OFFLINE_PHYSICAL_LAYOUT_SIMULATION_NO_FLASH",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "transition": {
            "from": {"firmware": "F207", "sha256": sha(old_candidate)},
            "to": {"firmware": "F209", "sha256": sha(new_candidate)},
            "store": {"format": "F211 JFFS2", "sha256": sha(store)},
        },
        "write_contract": {
            "physical_partition": "mtd4/linux_live",
            "physical_offset": f"0x{MTD4_OFFSET:06x}",
            "erase_write_bytes": PREFIX_SIZE,
            "preserved_tail_offset": f"0x{PREFIX_SIZE:06x}",
            "preserved_tail_bytes": STORE_SIZE,
            "full_mtd4_erase_allowed": False,
            "store_reset_requires_separate_authorization": True,
        },
        "before": before,
        "after": after,
        "checks": checks,
        "hardware_actions": {"router": False, "uart": False, "flash": False},
        "authorization": {"granted": False, "executor_emitted": False},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
