from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import analyze_f168_2g_tx_evidence as analysis  # noqa: E402
import build_f168_2g_tx_diag_from_f167 as f168  # noqa: E402


class F168TwoGTxDiagTests(unittest.TestCase):
    def test_loader_patch_changes_only_diagnostic_bits(self) -> None:
        sample = b" ".join(old for old, _new in f168.REPLACEMENTS)
        patched, report = f168.patch_loader(sample)
        self.assertGreater(len(patched), len(sample))
        for old, new in f168.REPLACEMENTS:
            self.assertNotIn(old, patched)
            self.assertIn(new, patched)
        self.assertEqual(6, len(report["changes"]))

    def test_f167_evidence_maps_low_download_to_tx_path(self) -> None:
        summary = json.loads(analysis.DEFAULT_SUMMARY.read_text(encoding="utf-8"))
        result = analysis.analyze(summary)
        self.assertAlmostEqual(6.875, result["throughput"]["download_mbps"], places=3)
        self.assertAlmostEqual(15.130, result["throughput"]["upload_mbps"], places=3)
        self.assertFalse(result["direction_mapping"]["rtl_rx_is_primary_download_path"])
        self.assertFalse(result["driver_audit"]["rtl_rx_bottleneck_supported"])
        self.assertTrue(result["driver_audit"]["emac_interference_observed"])
        self.assertEqual(2, result["observations"]["emac_rx_restarts"])

    def test_trace_parser_distinguishes_ampdu_and_ring_pressure(self) -> None:
        trace = "\n".join((
            "OMRTLRA stage=tx-desc event=1 hw_rate=19 ampdu=1",
            "OMRTLRA stage=tx-desc event=2 hw_rate=19 ampdu=0",
            "OMRTLTXCLOSE id=1 queued=77 closed=0",
            "OMRTL stage=tx-complete id=9 queue=1 queued=14->14 progressed=0",
        ))
        result = analysis.parse_trace(trace)
        self.assertEqual(2, result["tx_desc_samples"])
        self.assertEqual(1, result["tx_desc_ampdu_samples"])
        self.assertEqual([19], result["tx_desc_hw_rates"])
        self.assertEqual(77, result["max_observed_queue"])

    def test_built_artifact_contract(self) -> None:
        manifest_path = f168.OUT / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("F168 has not been built yet")
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        self.assertEqual("openmitrastar.f168-2g-tx-diag-from-f167/v1", manifest["schema"])
        self.assertEqual("NOT_RUN", manifest["physical_validation"]["status"])
        self.assertFalse(manifest["physical_validation"]["improvement_claimed"])
        self.assertTrue(manifest["rootfs_patch"]["rootfs_diff"]["only_loader_changed"])
        self.assertEqual("byte-identical to F167", manifest["change_scope"]["kernel"])
        self.assertEqual("byte-identical to F167", manifest["change_scope"]["radio2g_modules"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
