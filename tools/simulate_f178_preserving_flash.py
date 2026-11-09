#!/usr/bin/env python3
"""Simulate a prefix-only mtd4 update that preserves the F178 store tail."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLASH_SIZE = 0x1000000
ERASE_SIZE = 0x10000
MTD3_OFFSET = 0x040000
MTD3_SIZE = 0x7A0000
MTD4_OFFSET = 0x7E0000
MTD4_SIZE = 0x7A0000
PREFIX_SIZE = 0x5E0000
STORE_OFFSET = MTD4_OFFSET + PREFIX_SIZE
STORE_SIZE = MTD4_SIZE - PREFIX_SIZE
MTD5_OFFSET = 0xF80000
MTD5_SIZE = 0x080000
DEFAULT_CANDIDATE = ROOT / "work/mission-state/q3-persistent-composite-f177-lyoko-package-manager-from-f176/build/openmitrastar-linux510-q3-persistent-f177-lyoko-package-manager-from-f176-LZMA-OFFLINE-NO-FLASH.webformat.bin"


def sha(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def simulate(candidate: bytes) -> dict[str, object]:
    if len(candidate) > PREFIX_SIZE:
        raise ValueError("candidate does not fit the F178 writable prefix")
    if any(value % ERASE_SIZE for value in (MTD4_OFFSET, PREFIX_SIZE, STORE_OFFSET, STORE_SIZE)):
        raise ValueError("F178 boundaries are not erase aligned")

    rng = random.Random(0xF178)
    flash = bytearray(rng.randbytes(FLASH_SIZE))
    store_pattern = bytes((index * 37 + 11) & 0xFF for index in range(STORE_SIZE))
    flash[STORE_OFFSET:STORE_OFFSET + STORE_SIZE] = store_pattern
    before = {
        "mtd3": sha(flash[MTD3_OFFSET:MTD3_OFFSET + MTD3_SIZE]),
        "store": sha(flash[STORE_OFFSET:STORE_OFFSET + STORE_SIZE]),
        "mtd5": sha(flash[MTD5_OFFSET:MTD5_OFFSET + MTD5_SIZE]),
    }

    flash[MTD4_OFFSET:MTD4_OFFSET + PREFIX_SIZE] = b"\xff" * PREFIX_SIZE
    flash[MTD4_OFFSET:MTD4_OFFSET + len(candidate)] = candidate
    after = {
        "mtd3": sha(flash[MTD3_OFFSET:MTD3_OFFSET + MTD3_SIZE]),
        "store": sha(flash[STORE_OFFSET:STORE_OFFSET + STORE_SIZE]),
        "mtd5": sha(flash[MTD5_OFFSET:MTD5_OFFSET + MTD5_SIZE]),
    }
    checks = {
        "candidate_prefix_matches": flash[MTD4_OFFSET:MTD4_OFFSET + len(candidate)] == candidate,
        "unused_prefix_erased": set(flash[MTD4_OFFSET + len(candidate):MTD4_OFFSET + PREFIX_SIZE]) <= {0xFF},
        "store_preserved": before["store"] == after["store"],
        "mtd3_preserved": before["mtd3"] == after["mtd3"],
        "mtd5_preserved": before["mtd5"] == after["mtd5"],
        "store_pattern_preserved": flash[STORE_OFFSET:STORE_OFFSET + STORE_SIZE] == store_pattern,
    }
    return {
        "schema": "openmitrastar.f178-prefix-flash-simulation/v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "candidate": {
            "bytes": len(candidate),
            "sha256": sha(candidate),
            "prefix_headroom_bytes": PREFIX_SIZE - len(candidate),
        },
        "layout": {
            "flash_size": FLASH_SIZE,
            "mtd4_offset": MTD4_OFFSET,
            "mtd4_size": MTD4_SIZE,
            "writable_prefix_size": PREFIX_SIZE,
            "store_offset": STORE_OFFSET,
            "store_size": STORE_SIZE,
        },
        "before": before,
        "after": after,
        "checks": checks,
        "hardware_actions": {"router": False, "uart": False, "mtd": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = simulate(args.candidate.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
