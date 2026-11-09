#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f105_2g_be_reclaim_kick_from_f104 as radio2g  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f159_2g_rtlpci_historical_fast_from_f158 as f159  # noqa: E402


class F159HistoricalRtlPciBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f159.SRC_BUILD / f"{f159.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f159.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_replaces_only_rtl_pci_and_integrity_metadata(self) -> None:
        allowed = {
            f159.RTL_PCI_ENTRY,
            radio2g.RADIO2G_HASHES,
            radio2g.RADIO2G_MANIFEST,
            engine.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_module_hash_and_f158_policy_are_exact(self) -> None:
        rtl_pci = self.new_map[f159.RTL_PCI_ENTRY]
        self.assertEqual(hashlib.sha256(rtl_pci).hexdigest(), f159.NEW_RTL_PCI_SHA)
        loader = self.new_map["usr/sbin/om-radio-modules"].decode("ascii")
        self.assertIn("hgw500_tx_queue_guard=0", loader)
        self.assertIn("hgw500_tx_reclaim_poll=0", loader)
        start = self.new_map[engine.START_ENTRY]
        self.assertIn(b"OMRADIO5_TXBA_POLICY disabled=1 source=f156", start)
        self.assertIn(b"OMQTN5G_BRIDGE_READY", start)


if __name__ == "__main__":
    unittest.main(verbosity=2)
