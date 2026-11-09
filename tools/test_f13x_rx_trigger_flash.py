from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/arm_f13x_rx_trigger_flash.ps1"


class F13xRxTriggerFlashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_supports_expected_profiles(self) -> None:
        for profile in ("F133", "F134", "F135"):
            self.assertIn(profile, self.text)
        self.assertIn("arm_f133_5g_disable_hr_timer_flash.ps1", self.text)
        self.assertIn("arm_f134_5g_vap_rf_hold_flash.ps1", self.text)
        self.assertIn("arm_f135_5g_core_hold_flash.ps1", self.text)

    def test_waits_for_rx_before_flash(self) -> None:
        self.assertIn("uart_tx_before_rx = $false", self.text)
        self.assertIn("armed_waiting_for_first_rx", self.text)
        self.assertIn("first_rx_seen_starting_flash", self.text)
        self.assertIn("trigger_timeout_no_rx", self.text)
        self.assertIn("-Execute", self.text)

    def test_no_blind_autobreak_unless_explicit(self) -> None:
        self.assertIn("[switch]$AllowBlindAutobreak", self.text)
        self.assertIn("$blindAtguAfterNoRxSeconds = if ($AllowBlindAutobreak) { 8 } else { 0 }", self.text)
        self.assertIn('if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }', self.text)

    def test_preserves_live_slot_scope(self) -> None:
        self.assertIn("expected_full_slot_crc32", self.text)
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)
        self.assertNotIn("qtnboot", self.text)


if __name__ == "__main__":
    unittest.main()
