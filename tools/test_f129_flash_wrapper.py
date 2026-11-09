from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/arm_f129_5g_oem_region_txpower_flash.ps1"


class F129FlashWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WRAPPER.read_text(encoding="utf-8")

    def test_wrapper_is_pinned_to_f129_candidate(self) -> None:
        self.assertIn("q3-persistent-composite-f129-5g-oem-region-txpower-from-f128", self.text)
        self.assertIn("OPENMITRASTAR_Q3_F129_5G_OEM_REGION_TXPOWER_FROM_F128", self.text)
        self.assertIn("0fd2edc274d13801b6e3c1af4732812c1d9dc9f8064f330a3d9e5650e97e21f0", self.text)
        self.assertIn('$ExpectedBytes = "4373785"', self.text)
        self.assertIn('$ExpectedCandidateCrc32 = "c314002c"', self.text)
        self.assertIn('$ExpectedFullSlotCrc32 = "d48200d4"', self.text)

    def test_wrapper_expects_current_f128_live_slot(self) -> None:
        self.assertIn('[string]$CurrentLiveCrc32 = "fa2a5be1"', self.text)

    def test_wrapper_delegates_to_existing_bootbase_flash_backend(self) -> None:
        self.assertIn("run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py", self.text)
        self.assertIn("q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1", self.text)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", self.text)
        self.assertIn("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", self.text)
        self.assertIn("[int]$BlindAtguAfterNoRxSeconds = 8", self.text)
        self.assertIn("blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds", self.text)

    def test_wrapper_keeps_flash_scope_on_mtd4_live_slot(self) -> None:
        self.assertIn("F129 dry-run passed; no router writes", self.text)
        self.assertIn("F129 flash helper running in foreground", self.text)
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)
        self.assertNotIn("qtnboot", self.text)


if __name__ == "__main__":
    unittest.main()
