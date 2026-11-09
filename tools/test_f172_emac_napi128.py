from __future__ import annotations

import json
import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import analyze_f172_emac_starvation as analysis  # noqa: E402
import compose_f172_emac_napi128 as f172  # noqa: E402
import evaluate_f172_emac_napi128_result as evaluator  # noqa: E402


DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
F171 = ROOT / "work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build"
F171_BASE = "openmitrastar-linux510-q3-persistent-f171-lyoko-foundation-health-fix-LZMA-OFFLINE-NO-FLASH"


class F172EmacNapi128Tests(unittest.TestCase):
    def test_single_source_variable_is_napi_weight_128(self) -> None:
        text = DRIVER.read_text(encoding="utf-8")
        self.assertIn("#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t128", text)
        self.assertIn("QTN_TOPAZ_EMAC_RX_RING_COUNT\t128", text)
        self.assertIn("QTN_TOPAZ_EMAC_RX_RESTART_POKES\t16", text)
        self.assertIn("QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS\t10000", text)
        self.assertIn("netif_napi_add(ndev, &emac->napi, qtn_emac_poll,", text)
        self.assertIn("QTN_TOPAZ_EMAC_NAPI_WEIGHT);", text)
        self.assertIn('"napi_weight=%u\\n', text)
        self.assertNotIn("netif_napi_add(ndev, &emac->napi, qtn_emac_poll, 64);", text)

        reconstructed_f167 = text.replace(
            "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t128\n"
            "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t128\n",
            "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t128\n",
        ).replace(
            '\t\t"napi_weight=%u\\npoll_ticks=%u\\npoll_napi_schedules=%u\\npoll_forced_napi=%u\\n"',
            '\t\t"poll_ticks=%u\\npoll_napi_schedules=%u\\npoll_forced_napi=%u\\n"',
        ).replace(
            "READ_ONCE(emac->irq_napi_schedules), QTN_TOPAZ_EMAC_NAPI_WEIGHT,\n"
            "\t\tREAD_ONCE(emac->poll_ticks),",
            "READ_ONCE(emac->irq_napi_schedules), READ_ONCE(emac->poll_ticks),",
        ).replace(
            "netif_napi_add(ndev, &emac->napi, qtn_emac_poll,\n"
            "\t\t\t QTN_TOPAZ_EMAC_NAPI_WEIGHT);",
            "netif_napi_add(ndev, &emac->napi, qtn_emac_poll, 64);",
        )
        self.assertEqual(
            "f6f9794fba104dd3a46835bc3300f885fefc6c9ab69976daf3485646dfc76018",
            hashlib.sha256(reconstructed_f167.encode()).hexdigest(),
        )

    def test_physical_evidence_concentrates_in_download_window(self) -> None:
        result = analysis.analyze(
            json.loads(analysis.DEFAULT_SUMMARY.read_text(encoding="utf-8")),
            analysis.load_samples(analysis.DEFAULT_SAMPLES),
        )
        self.assertEqual(133, result["first_download_window_delta"]["napi_budget_exhaustions"])
        self.assertEqual(617, result["first_download_window_delta"]["dma_no_rx_desc_samples"])
        self.assertEqual(2, result["first_download_window_delta"]["rx_restart_reason_no_desc"])
        self.assertEqual(0, result["remaining_window_delta"]["napi_budget_exhaustions"])
        self.assertTrue(result["derived"]["all_new_no_rx_desc_restarts_in_first_window"])
        self.assertFalse(result["candidate"]["improvement_claimed"])

    def test_built_contract(self) -> None:
        manifest_path = f172.OUT / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("F172 has not been built yet")
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        self.assertEqual("openmitrastar.f172-emac-napi128-from-f171/v1", manifest["schema"])
        self.assertEqual("NOT_RUN", manifest["physical_validation"]["status"])
        self.assertFalse(manifest["physical_validation"]["improvement_claimed"])
        self.assertEqual("qtn-topaz-emac NAPI weight 64 -> 128", manifest["change_scope"]["single_variable"])
        f171_rootfs = F171 / f"{F171_BASE}.rootfs.squashfs"
        f172_rootfs = f172.OUT / f"{f172.BASE}.rootfs.squashfs"
        self.assertEqual(f172.sha256(f171_rootfs), f172.sha256(f172_rootfs))
        self.assertNotEqual(
            json.loads((F171 / "manifest.json").read_text(encoding="ascii"))["artifacts"]["kernel_lzma"]["sha256"],
            manifest["artifacts"]["kernel_lzma"]["sha256"],
        )
        self.assertEqual("PASS", manifest["binary_contract"]["result"])
        self.assertEqual(128, manifest["binary_contract"]["decimal"])

    def test_physical_evaluator_requires_real_improvement_and_zero_restarts(self) -> None:
        baseline = json.loads(analysis.DEFAULT_SUMMARY.read_text(encoding="utf-8"))
        candidates = []
        for download_mbps in (8.0, 8.1, 8.2):
            run = json.loads(json.dumps(baseline))
            run["controller_download"]["speed_Bps"] = download_mbps * 1_000_000 / 8
            run["controller_upload"]["speed_Bps"] = 1_900_000
            run["emac_stats_delta"].update({
                "irq_no_rx_desc": 0,
                "dma_no_rx_desc_samples": 0,
                "napi_budget_exhaustions": 0,
                "rx_restart_total": 0,
                "rx_restart_reason_no_desc": 0,
                "rx_alloc_failures": 0,
            })
            run["netdev_delta"]["wlan0"].update({
                "rx_errs": 0, "tx_errs": 0, "rx_drop": 0, "tx_drop": 0,
            })
            candidates.append(run)
        result = evaluator.evaluate(baseline, candidates)
        self.assertEqual("PASS", result["status"])
        candidates[0]["emac_stats_delta"]["rx_restart_total"] = 1
        self.assertEqual("FAIL", evaluator.evaluate(baseline, candidates)["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
