from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/arm_f133_wait_powercycle_flash.ps1"


class F133WaitPowercycleFlashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_waiter_targets_f133_and_current_f132_slot(self) -> None:
        self.assertIn("arm_f133_5g_disable_hr_timer_flash.ps1", self.text)
        self.assertIn("f133-5g-disable-hr-timer-from-f132", self.text)
        self.assertIn('"d11c5cbd"', self.text)
        self.assertIn('"e692b50c"', self.text)

    def test_waiter_uses_rx_gate_by_default(self) -> None:
        self.assertIn("[int]$NoRxAbortSeconds = 180", self.text)
        self.assertIn('"-NoRxAbortSeconds", "$NoRxAbortSeconds"', self.text)
        self.assertIn('"-BlindAtguAfterNoRxSeconds", "$blindAtguAfterNoRxSeconds"', self.text)
        self.assertIn("OMF133_WAIT_POWER_CYCLE_RX_GATE=1", self.text)
        self.assertIn("if ($AllowBlindAutobreak) { $args += \"-AllowBlindAutobreak\" }", self.text)

    def test_waiter_preserves_mtd4_wrapper_scope(self) -> None:
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)
        self.assertNotIn("qtnboot", self.text)


if __name__ == "__main__":
    unittest.main()
