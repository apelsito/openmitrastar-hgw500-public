from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import compose_f166_emac_telemetry as f166  # noqa: E402


class F166EmacTelemetryTests(unittest.TestCase):
    def test_source_exposes_read_only_cause_counters(self) -> None:
        source = (
            ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
        ).read_text(encoding="utf-8")
        for marker in (
            "DEVICE_ATTR_RO(lyoko_emac_stats)",
            "irq_napi_schedules",
            "napi_budget_exhaustions",
            "rx_head_dma_owned_samples",
            "dma_rx_stopped_samples",
            "dma_no_rx_desc_samples",
            "dma_rx_missed_samples",
            "rx_restart_reason_stagnant",
        ):
            self.assertIn(marker, source)
        self.assertIn("QTN_TOPAZ_EMAC_RX_RESTART_POKES\t16", source)
        self.assertIn("QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS\t10000", source)

    def test_built_artifact_contract(self) -> None:
        manifest_path = f166.OUT / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("F166 has not been built yet")
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        self.assertEqual("openmitrastar.f166-emac-cause-telemetry/v1", manifest["schema"])
        self.assertTrue(manifest["candidate_eligible"])
        self.assertTrue(manifest["flash_supported"])
        self.assertEqual("0x90960000+0x00620000, Linux root=31:3", manifest["layout"]["mtd_mapping"].split("read-only mtd-rom ", 1)[1])
        raw = (f166.OUT / f"{f166.BASE}.kernel.raw.bin").read_bytes()
        self.assertIn(b"lyoko_emac_stats", raw)

    def test_flash_wrapper_is_uart_only_and_pinned_to_f165(self) -> None:
        text = (ROOT / "tools/build_flash_test_f166_emac_telemetry.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$CurrentLiveCrc32 = "5123431d"', text)
        self.assertIn('"--transport", "uart-ymodem"', text)
        self.assertIn('target = "mtd4/linux_live"', text)
        self.assertNotIn("tftpboot", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
