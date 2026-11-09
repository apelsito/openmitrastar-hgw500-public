#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f153_5g_rx_inactivity_refresh_from_f152 as pair_builder  # noqa: E402
import build_f155_5g_txpool_trace_from_f154 as f155  # noqa: E402


class F155TxPoolTraceBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f155.SRC_BUILD / f"{f155.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        with f155.variant_context():
            cls.patched, cls.report = pair_builder.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_replaces_only_qdrv_and_integrity_metadata(self) -> None:
        allowed = {
            engine.QDRV_ENTRY,
            engine.START_ENTRY,
            engine.DRIVER_CONTRACT_ENTRY,
            engine.HASHES_ENTRY,
            engine.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(self.old_map[engine.WLAN_ENTRY], self.new_map[engine.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_txpool_markers_hash_and_contract_are_exact(self) -> None:
        qdrv = self.new_map[engine.QDRV_ENTRY]
        self.assertEqual(hashlib.sha256(qdrv).hexdigest(), f155.NEW_QDRV_SHA)
        self.assertIn(b"OMQDRVTXGSO stage=segmented", qdrv)
        self.assertIn(b"OMQDRVTXPOOL total=", qdrv)
        self.assertIn(b"openmitrastar_auc_busy_total", qdrv)
        start = self.new_map[engine.START_ENTRY].decode("ascii")
        contract = self.new_map[engine.DRIVER_CONTRACT_ENTRY].decode("ascii")
        self.assertIn(f"expected_qdrv_sha={f155.NEW_QDRV_SHA}", start)
        self.assertIn(f"QDRV_SHA256={f155.NEW_QDRV_SHA}", contract)
        self.assertIn(f"WLAN_SHA256={f155.WLAN_SHA}", contract)


if __name__ == "__main__":
    unittest.main(verbosity=2)
