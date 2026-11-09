#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f161_2g_oem_tx_report_from_f160 as f161  # noqa: E402


class F161OemTxReportBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f161.SRC_BUILD / f"{f161.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f161.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_only_loader_and_integrity_metadata_change(self) -> None:
        allowed = {f161.PATCH_ENTRY, engine.HASHES_ENTRY, engine.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(self.old_map[engine.QDRV_ENTRY], self.new_map[engine.QDRV_ENTRY])
        self.assertEqual(self.old_map[engine.WLAN_ENTRY], self.new_map[engine.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_loader_enables_oem_tx_report_and_keeps_be_summary(self) -> None:
        loader = self.new_map[f161.PATCH_ENTRY].decode("ascii")
        self.assertIn("hgw500_oem_tx_report=1", loader)
        self.assertIn("hgw500_oem_tx_report=Y", loader)
        self.assertIn("hgw500_be_tx_summary=1", loader)
        self.assertIn("hgw500_tx_reclaim_poll=0", loader)


if __name__ == "__main__":
    unittest.main(verbosity=2)
