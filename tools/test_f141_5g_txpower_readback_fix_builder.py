#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f140_5g_txpower_contract_fix_from_f139 as f140  # noqa: E402
import build_f141_5g_txpower_readback_fix_from_f140 as f141  # noqa: E402


class F141TxPowerReadbackFixBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f140.OUT / f"{f140.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f141.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_only_start_hashes_and_padding_change(self) -> None:
        allowed = {f141.START_ENTRY, f141.HASHES_ENTRY, f141.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue({f141.START_ENTRY, f141.HASHES_ENTRY}.issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_txpower_readback_accepts_active_equals_separator(self) -> None:
        start = self.new_map[f141.START_ENTRY].decode("ascii")
        self.assertNotIn("grep -Fq 'Tx-Power:21 dBm'", start)
        self.assertIn("grep -Eq 'Tx-Power[:=]21 dBm'", start)
        self.assertIn("OMRADIO5_TXPOWER_LIMIT dbm=21", start)


if __name__ == "__main__":
    unittest.main(verbosity=2)
