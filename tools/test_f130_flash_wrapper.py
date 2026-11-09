from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/arm_f130_5g_rf_before_vap_flash.ps1"


class F130FlashWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WRAPPER.read_text(encoding="utf-8")

    def test_wrapper_is_pinned_to_f130_candidate(self) -> None:
        self.assertIn("q3-persistent-composite-f130-5g-rf-before-vap-from-f129", self.text)
        self.assertIn("OPENMITRASTAR_Q3_F130_5G_RF_BEFORE_VAP_FROM_F129", self.text)
        self.assertIn("6333bfce85e303bce41ca3ea299c7659340743c753ca500b9f68550e5d35f6d4", self.text)
        self.assertIn('$ExpectedBytes = "4373906"', self.text)
        self.assertIn('$ExpectedCandidateCrc32 = "694ca7fe"', self.text)
        self.assertIn('$ExpectedFullSlotCrc32 = "9ac5a77c"', self.text)

    def test_wrapper_expects_current_f129_live_slot(self) -> None:
        self.assertIn('[string]$CurrentLiveCrc32 = "d48200d4"', self.text)

    def test_wrapper_delegates_to_existing_bootbase_flash_backend(self) -> None:
        self.assertIn("run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py", self.text)
        self.assertIn("q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1", self.text)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", self.text)
        self.assertIn("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", self.text)
        self.assertIn("[int]$BlindAtguAfterNoRxSeconds = 8", self.text)
        self.assertIn("blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds", self.text)

    def test_wrapper_keeps_flash_scope_on_mtd4_live_slot(self) -> None:
        self.assertIn("F130 dry-run passed; no router writes", self.text)
        self.assertIn("F130 flash helper running in foreground", self.text)
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)
        self.assertNotIn("qtnboot", self.text)


if __name__ == "__main__":
    unittest.main()
