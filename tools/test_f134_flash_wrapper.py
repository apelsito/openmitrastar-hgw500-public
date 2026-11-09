from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/arm_f134_5g_vap_rf_hold_flash.ps1"
WAIT_WRAPPER = ROOT / "tools/arm_f134_wait_powercycle_flash.ps1"


class F134FlashWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WRAPPER.read_text(encoding="utf-8")
        cls.wait_text = WAIT_WRAPPER.read_text(encoding="utf-8")

    def test_wrapper_is_pinned_to_f134_candidate(self) -> None:
        self.assertIn("q3-persistent-composite-f134-5g-vap-rf-hold-from-f133", self.text)
        self.assertIn("OPENMITRASTAR_Q3_F134_5G_VAP_RF_HOLD_FROM_F133", self.text)
        self.assertIn("0ee7360a839274db8d6ffa121e9173f6c409aaeea202893246cf85cc07625ae0", self.text)
        self.assertIn('$ExpectedBytes = "4372987"', self.text)
        self.assertIn('$ExpectedCandidateCrc32 = "ac4d214e"', self.text)
        self.assertIn('$ExpectedFullSlotCrc32 = "218cf82a"', self.text)

    def test_wrapper_defaults_to_current_f132_live_slot(self) -> None:
        self.assertIn('[string]$CurrentLiveCrc32 = "d11c5cbd"', self.text)
        self.assertIn('[string]$CurrentLiveCrc32 = "d11c5cbd"', self.wait_text)
        self.assertIn('[int]$NoRxAbortSeconds = 180', self.wait_text)
        self.assertIn("OMF134_WAIT_POWER_CYCLE_RX_GATE=1", self.wait_text)
        self.assertIn('"-NoRxAbortSeconds", "$NoRxAbortSeconds"', self.wait_text)
        self.assertIn('"-BlindAtguAfterNoRxSeconds", "$blindAtguAfterNoRxSeconds"', self.wait_text)

    def test_wrapper_delegates_to_existing_bootbase_flash_backend(self) -> None:
        self.assertIn("run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py", self.text)
        self.assertIn("q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1", self.text)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", self.text)
        self.assertIn("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", self.text)
        self.assertIn("[int]$BlindAtguAfterNoRxSeconds = 8", self.text)
        self.assertIn("blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds", self.text)

    def test_wrapper_keeps_flash_scope_on_mtd4_live_slot(self) -> None:
        self.assertIn("F134 dry-run passed; no router writes", self.text)
        self.assertIn("F134 flash helper running in foreground", self.text)
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)
        self.assertNotIn("qtnboot", self.text)


if __name__ == "__main__":
    unittest.main()
