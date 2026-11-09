from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/arm_f123_5g_vap_create_observe_flash.ps1"


class F123FlashWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WRAPPER.read_text(encoding="utf-8")

    def test_wrapper_is_pinned_to_f123_candidate(self) -> None:
        self.assertIn("q3-persistent-composite-f123-5g-vap-create-observe-from-f122", self.text)
        self.assertIn("OPENMITRASTAR_Q3_F123_5G_VAP_CREATE_OBSERVE_FROM_F122", self.text)
        self.assertIn("3d3de5b9aee4f0a386b9485a02780841d5eda038b1dc2ac21cd299a48602fad9", self.text)
        self.assertIn('$ExpectedBytes = "4372985"', self.text)
        self.assertIn('$ExpectedCandidateCrc32 = "7679e291"', self.text)
        self.assertIn('$ExpectedFullSlotCrc32 = "43725507"', self.text)

    def test_wrapper_expects_current_f122_live_slot(self) -> None:
        self.assertIn('[string]$CurrentLiveCrc32 = "fc3c3d99"', self.text)

    def test_wrapper_delegates_to_bootbase_autoboot_flash_backend(self) -> None:
        self.assertIn("run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py", self.text)
        self.assertIn("q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1", self.text)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", self.text)
        self.assertIn("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", self.text)


if __name__ == "__main__":
    unittest.main()
