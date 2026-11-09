#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f77_2g_fast_5g_stage_guard.ps1"
MONITOR = ROOT / "tools/monitor_f77_flash_then_stage_gate.ps1"
STAGE = ROOT / "tools/post_flash_f77_stage_gate.ps1"
ARM = ROOT / "tools/arm_f77_flash_then_stage_gate.ps1"


class F77FlashWrapperTests(unittest.TestCase):
    def test_flash_wrapper_points_at_f77_build_and_ack(self) -> None:
        text = FLASH.read_text(encoding="utf-8")
        self.assertIn(
            "q3-persistent-composite-f77-2g-mcs7-noguard-5g-stage-guard\\build",
            text,
        )
        self.assertIn(
            "OPENMITRASTAR_Q3_F77_2G_MCS7_NOGUARD_5G_STAGE_GUARD_MTD4_FLASH_05EA7BAE",
            text,
        )
        self.assertIn("[int]$NoRxAbortSeconds = 300", text)
        self.assertIn("OMF77_FLASH_WRAPPER_DRY_RUN_PASS=1", text)
        self.assertNotIn("F76", text)
        self.assertNotIn("f76", text)

    def test_monitor_runs_f77_stage_gate_and_detects_rx_zero(self) -> None:
        text = MONITOR.read_text(encoding="utf-8")
        self.assertIn("post_flash_f77_stage_gate.ps1", text)
        self.assertIn("PASS_F77_FLASH_2G_AND_5G_MODULE_STAGE", text)
        self.assertIn("BLOCKED_BY_FLASH_UART_RX_ZERO", text)
        self.assertIn("Test-F77FlashUartRxZero", text)
        self.assertNotIn("F76", text)
        self.assertNotIn("f76", text)

    def test_stage_gate_uses_f77_markers(self) -> None:
        text = STAGE.read_text(encoding="utf-8")
        self.assertIn("OMF77_STAGE_MODULES_BEGIN", text)
        self.assertIn("PASS_F77_2G_AND_5G_MODULE_STAGE", text)
        self.assertIn("openmitrastar.f77-stage-gate/v1", text)
        self.assertNotIn("F76", text)
        self.assertNotIn("f76", text)

    def test_auto_arm_starts_flash_and_monitor_with_same_stamp(self) -> None:
        text = ARM.read_text(encoding="utf-8")
        self.assertIn("openmitrastar.f77-auto-arm/v1", text)
        self.assertIn("flash_f77_2g_fast_5g_stage_guard.ps1", text)
        self.assertIn("monitor_f77_flash_then_stage_gate.ps1", text)
        self.assertIn("OMF77_AUTO_ARM_DRY_RUN_PASS=1", text)
        self.assertIn("OMF77_AUTO_ARMED=1", text)
        self.assertIn("OPENMITRASTAR_Q3_F77_2G_MCS7_NOGUARD_5G_STAGE_GUARD_MTD4_FLASH_05EA7BAE", text)


if __name__ == "__main__":
    unittest.main()
