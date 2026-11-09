#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "tools/run_qtn_w3_final_5g_open_pipeline.py"


class FinalOpenPipelineTests(unittest.TestCase):
    def test_pins_nowdt_diagnostic_image_and_open_stage(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("linux510-product-cgi-nowdt-diagnostic-v1-RAM-ONLY.bin", text)
        self.assertIn("b63a31eaa5104e77a7af5bf07197bf30f58b2925ab07e2580487b94a967e8f53", text)
        self.assertIn("--use-current-no-watchdog-boot", text)
        self.assertIn("--no-hw-watchdog", text)
        self.assertIn("--skip-ioss-reset-pulse", text)
        self.assertIn("--no-uart-reboot-on-failure", text)
        self.assertNotIn("linux510-product-private-checkpoint-v1-RAM-ONLY.bin", text)
        self.assertIn("run_qtn_w3_native_open_ap.py", text)
        self.assertIn("security=OPEN", text)

    def test_cold_boot_precedes_hbm_and_qdrv(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertLess(text.index("cold_boot(args.port"), text.index("run_qtn_w3_switch_emac_handoff.py"))
        self.assertIn('parser.add_argument("--reboot-current", action="store_true")', text)
        self.assertLess(text.index("run_qtn_w3_switch_emac_handoff.py"), text.index("run_qtn_w3_qdrv_hostlink_core.py"))
        self.assertLess(text.index("run_qtn_w3_qdrv_hostlink_core.py"), text.index("run_qtn_w3_native_open_ap.py"))

    def test_ram_only_and_no_secret(self):
        text = PIPELINE.read_text(encoding="utf-8").lower()
        for forbidden in ("flash_erase", "mtd write", "saveenv", "nandwrite", "psk-file"):
            self.assertNotIn(forbidden, text)
        self.assertIn('"flash": false', text)

    def test_dry_run(self):
        result = subprocess.run(
            [sys.executable, "-B", str(PIPELINE)], cwd=ROOT,
            text=True, capture_output=True, check=True,
        )
        self.assertIn("W3_FINAL_5G_OPEN_PIPELINE_DRY_RUN_PASS=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
