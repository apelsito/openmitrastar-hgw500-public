#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f141_5g_txpower_readback_fix_from_f140 as f141  # noqa: E402
import build_f142_5g_disassoc_atomic_from_f141 as f142  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F142DisassocAtomicBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f141.OUT / f"{f141.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f142.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_qdrv_patch_is_exactly_two_bytes(self) -> None:
        old = self.old_map[f142.QDRV_ENTRY]
        new = self.new_map[f142.QDRV_ENTRY]
        self.assertEqual(f142.OLD_QDRV_SHA, sha256(old))
        self.assertEqual(len(old), len(new))
        changed = [index for index, pair in enumerate(zip(old, new)) if pair[0] != pair[1]]
        self.assertEqual(
            [f142.QDRV_DISASSOC_GFP_FILE_OFF, f142.QDRV_DISASSOC_GFP_FILE_OFF + 1],
            changed,
        )
        self.assertEqual(f142.OLD_GFP_BYTES, old[f142.QDRV_DISASSOC_GFP_FILE_OFF:f142.QDRV_DISASSOC_GFP_FILE_OFF + 2])
        self.assertEqual(f142.NEW_GFP_BYTES, new[f142.QDRV_DISASSOC_GFP_FILE_OFF:f142.QDRV_DISASSOC_GFP_FILE_OFF + 2])

    def test_patch_scope_preserves_wlan_and_fixed_payload(self) -> None:
        allowed = {f142.QDRV_ENTRY, f142.START_ENTRY, f142.DRIVER_CONTRACT_ENTRY,
                   f142.HASHES_ENTRY, f142.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue({f142.QDRV_ENTRY, f142.START_ENTRY,
                         f142.DRIVER_CONTRACT_ENTRY, f142.HASHES_ENTRY}.issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(self.old_map[f142.WLAN_ENTRY], self.new_map[f142.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_contract_and_start_expect_patched_qdrv(self) -> None:
        new_qdrv = self.new_map[f142.QDRV_ENTRY]
        new_hash = sha256(new_qdrv)
        self.assertIn(f"QDRV_SHA256={new_hash}", self.new_map[f142.DRIVER_CONTRACT_ENTRY].decode("ascii"))
        self.assertIn(new_hash, self.new_map[f142.START_ENTRY].decode("ascii"))
        self.assertNotIn(f142.OLD_QDRV_SHA, self.new_map[f142.START_ENTRY].decode("ascii"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
