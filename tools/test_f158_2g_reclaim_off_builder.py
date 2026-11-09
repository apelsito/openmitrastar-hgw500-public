#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f158_2g_reclaim_off_from_f157 as f158  # noqa: E402


class F158ReclaimOffBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f158.SRC_BUILD / f"{f158.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f158.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_only_loader_changes(self) -> None:
        allowed = {f158.PATCH_ENTRY, engine.HASHES_ENTRY, engine.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_loader_matches_historical_fast_profile(self) -> None:
        loader = self.new_map[f158.PATCH_ENTRY].decode("ascii")
        self.assertIn("hgw500_tx_queue_guard=0", loader)
        self.assertIn("hgw500_tx_queue_guard_high=64", loader)
        self.assertIn("hgw500_tx_queue_guard_low=32", loader)
        self.assertIn("hgw500_tx_reclaim_poll=0", loader)
        self.assertIn("hgw500_tx_reclaim_poll=N", loader)
        self.assertNotIn(f158.OLD_LOAD, loader)


if __name__ == "__main__":
    unittest.main(verbosity=2)
