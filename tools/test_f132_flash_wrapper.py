from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/arm_f132_5g_hrflags_skip_epilogue_flash.ps1"


class F132FlashWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WRAPPER.read_text(encoding="utf-8")

    def test_wrapper_is_pinned_to_f132_candidate(self) -> None:
        self.assertIn("q3-persistent-composite-f132-5g-hrflags-skip-epilogue-from-f129", self.text)
        self.assertIn("OPENMITRASTAR_Q3_F132_5G_HRFLAGS_SKIP_EPILOGUE_FROM_F129", self.text)
        self.assertIn("8e4a13db016a4caabe921d85351d693c51701520ee33bd4c3d01d1bde1d81a98", self.text)
        self.assertIn('$ExpectedBytes = "4373101"', self.text)
        self.assertIn('$ExpectedCandidateCrc32 = "628125fb"', self.text)
        self.assertIn('$ExpectedFullSlotCrc32 = "d11c5cbd"', self.text)

    def test_wrapper_expects_current_f131_live_slot(self) -> None:
        self.assertIn('[string]$CurrentLiveCrc32 = "b168f55e"', self.text)

    def test_wrapper_delegates_to_existing_bootbase_flash_backend(self) -> None:
        self.assertIn("run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py", self.text)
        self.assertIn("q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1", self.text)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", self.text)
        self.assertIn("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", self.text)
        self.assertIn("[int]$BlindAtguAfterNoRxSeconds = 8", self.text)
        self.assertIn("blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds", self.text)

    def test_wrapper_keeps_flash_scope_on_mtd4_live_slot(self) -> None:
        self.assertIn("F132 dry-run passed; no router writes", self.text)
        self.assertIn("F132 flash helper running in foreground", self.text)
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)
        self.assertNotIn("qtnboot", self.text)


if __name__ == "__main__":
    unittest.main()
