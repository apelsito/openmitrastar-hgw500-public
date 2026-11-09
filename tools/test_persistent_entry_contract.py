#!/usr/bin/env python3
from pathlib import Path

import verify_persistent_entry_contract as verifier


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work/mission-state"
F93 = BASE / (
    "q3-persistent-composite-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92/build/"
    "openmitrastar-linux510-q3-persistent-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92-LZMA-OFFLINE-NO-FLASH.decompressed.bin"
)
F94 = BASE / (
    "q3-persistent-composite-f94-2g-mcs15-ht40sgi-descfix-after-f93/build/"
    "openmitrastar-linux510-q3-persistent-f94-2g-mcs15-ht40sgi-descfix-after-f93-LZMA-OFFLINE-NO-FLASH.decompressed.bin"
)
F95 = BASE / (
    "q3-persistent-composite-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93/build/"
    "openmitrastar-linux510-q3-persistent-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93-LZMA-OFFLINE-NO-FLASH.decompressed.bin"
)


def test_f95_preserves_persistent_entry_contract() -> None:
    base = F93.read_bytes()
    candidate = F95.read_bytes()
    assert verifier.cpio_layout(base) == verifier.cpio_layout(candidate)
    offset = verifier.ENTRY_OFFSET
    assert candidate[offset:offset + verifier.ENTRY_SAMPLE_BYTES] == base[offset:offset + verifier.ENTRY_SAMPLE_BYTES]


def test_f94_is_rejected_by_persistent_entry_contract() -> None:
    base = F93.read_bytes()
    candidate = F94.read_bytes()
    assert verifier.cpio_layout(base)["cpio_end"] != verifier.cpio_layout(candidate)["cpio_end"]
    offset = verifier.ENTRY_OFFSET
    assert base[offset:offset + 16] != b"\x00" * 16
    assert candidate[offset:offset + 16] == b"\x00" * 16
    assert candidate[offset + 2356:offset + 2356 + 16] == base[offset:offset + 16]
