from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import compose_f167_emac_ownership_fix as f167  # noqa: E402


class F167EmacOwnershipFixTests(unittest.TestCase):
    def test_ownership_counters_are_rx_only(self) -> None:
        source = (
            ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
        ).read_text(encoding="utf-8")
        tx_start = source.index("static void qtn_emac_tx_reclaim_locked")
        tx_end = source.index("static void qtn_emac_free_tx_buffers", tx_start)
        rx_start = source.index("static int qtn_emac_rx_poll")
        rx_end = source.index("static int qtn_emac_poll", rx_start)
        tx_reclaim = source[tx_start:tx_end]
        rx_poll = source[rx_start:rx_end]
        self.assertNotIn("rx_head_dma_owned_samples++", tx_reclaim)
        self.assertNotIn("rx_head_cpu_owned_descs++", tx_reclaim)
        self.assertIn("rx_head_dma_owned_samples++", rx_poll)
        self.assertIn("rx_head_cpu_owned_descs++", rx_poll)

    def test_built_artifact_contract(self) -> None:
        manifest_path = f167.OUT / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("F167 has not been built yet")
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        self.assertEqual("openmitrastar.f167-emac-ownership-fix/v1", manifest["schema"])
        self.assertTrue(manifest["candidate_eligible"])
        self.assertTrue(manifest["flash_supported"])
        self.assertEqual("unchanged from F165", manifest["change_scope"]["datapath_behavior"])
        raw = (f167.OUT / f"{f167.BASE}.kernel.raw.bin").read_bytes()
        self.assertIn(b"lyoko_emac_stats", raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)

