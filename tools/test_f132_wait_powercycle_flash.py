from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/arm_f132_wait_powercycle_flash.ps1"


class F132WaitPowercycleFlashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_waiter_targets_f132_and_current_f131_slot(self) -> None:
        self.assertIn("arm_f132_5g_hrflags_skip_epilogue_flash.ps1", self.text)
        self.assertIn("f132-5g-hrflags-skip-epilogue-from-f129", self.text)
        self.assertIn('"b168f55e"', self.text)
        self.assertIn('"d11c5cbd"', self.text)

    def test_waiter_uses_rx_gate_for_physical_powercycle_window(self) -> None:
        self.assertIn('[int]$NoRxAbortSeconds = 180', self.text)
        self.assertIn('"-NoRxAbortSeconds", "$NoRxAbortSeconds"', self.text)
        self.assertIn('"-BlindAtguAfterNoRxSeconds", "$blindAtguAfterNoRxSeconds"', self.text)
        self.assertIn("OMF132_WAIT_POWER_CYCLE_RX_GATE=1", self.text)
        self.assertIn("OMF132_WAIT_POWER_CYCLE_ARMED=1", self.text)
        self.assertIn("OMF132_WAIT_POWER_CYCLE_ACTION=power_cycle_router_now", self.text)

    def test_waiter_preserves_mtd4_wrapper_scope(self) -> None:
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)
        self.assertNotIn("qtnboot", self.text)


if __name__ == "__main__":
    unittest.main()
