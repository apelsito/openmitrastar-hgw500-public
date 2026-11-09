#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f142_5g_disassoc_atomic_from_f141 as f142  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as f143  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F143DeferredDmaFreeBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f142.OUT / f"{f142.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f143.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_rebuilt_qdrv_has_expected_contract_markers(self) -> None:
        old = self.old_map[f143.QDRV_ENTRY]
        new = self.new_map[f143.QDRV_ENTRY]
        self.assertEqual(f143.OLD_QDRV_SHA, sha256(old))
        self.assertEqual(f143.NEW_QDRV_SHA, sha256(new))
        self.assertIn(b"OMQDRVHLINK stage=free-deferred", new)
        self.assertIn(b"OMQDRVHLINK stage=free-defer-alloc-failed", new)
        self.assertIn(b"OMQDRVHR stage=timer-disabled reason=hgw-v89", new)

    def test_patch_scope_preserves_wlan_and_fixed_payload(self) -> None:
        allowed = {
            f143.QDRV_ENTRY, f143.START_ENTRY, f143.DRIVER_CONTRACT_ENTRY,
            f143.HASHES_ENTRY, f143.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue({f143.QDRV_ENTRY, f143.START_ENTRY,
                         f143.DRIVER_CONTRACT_ENTRY, f143.HASHES_ENTRY}.issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(self.old_map[f143.WLAN_ENTRY], self.new_map[f143.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_contract_and_start_expect_rebuilt_qdrv(self) -> None:
        new_hash = sha256(self.new_map[f143.QDRV_ENTRY])
        self.assertIn(
            f"QDRV_SHA256={new_hash}",
            self.new_map[f143.DRIVER_CONTRACT_ENTRY].decode("ascii"),
        )
        start = self.new_map[f143.START_ENTRY].decode("ascii")
        self.assertIn(new_hash, start)
        self.assertNotIn(f143.OLD_QDRV_SHA, start)


if __name__ == "__main__":
    unittest.main(verbosity=2)
