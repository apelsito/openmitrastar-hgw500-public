#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f139_5g_txpower_limit_from_f138 as f139  # noqa: E402
import build_f140_5g_txpower_contract_fix_from_f139 as f140  # noqa: E402


class F140TxPowerContractFixBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f139.OUT / f"{f139.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f140.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_only_start_hashes_and_padding_change(self) -> None:
        allowed = {f140.START_ENTRY, f140.HASHES_ENTRY, f140.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue({f140.START_ENTRY, f140.HASHES_ENTRY}.issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_profile_override_uses_new_wlan_hash(self) -> None:
        start = self.new_map[f140.START_ENTRY].decode("ascii")
        self.assertNotIn(f"expected_wlan_sha={f140.OLD_WLAN_SHA}", start)
        self.assertEqual(1, start.count(f"expected_wlan_sha={f140.NEW_WLAN_SHA}"))
        self.assertIn("OMRADIO5_TXPOWER_LIMIT dbm=21", start)


if __name__ == "__main__":
    unittest.main(verbosity=2)
