#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f78_2g_fast_5g_precontrol_stage_guard.ps1"
MONITOR = ROOT / "tools/monitor_f78_flash_then_stage_gate.ps1"
STAGE = ROOT / "tools/post_flash_f78_stage_gate.ps1"
ARM = ROOT / "tools/arm_f78_flash_then_stage_gate.ps1"


class F78FlashWrapperTests(unittest.TestCase):
    def test_flash_wrapper_points_at_f78_build_and_ack(self) -> None:
        text = FLASH.read_text(encoding="utf-8")
        self.assertIn(
            "q3-persistent-composite-f78-2g-fast-5g-modules-precontrol-stage-guard\\build",
            text,
        )
        self.assertIn(
            "OPENMITRASTAR_Q3_F78_2G_FAST_5G_PRECONTROL_STAGE_GUARD_MTD4_FLASH_8E0CA679",
            text,
        )
        self.assertIn("[int]$NoRxAbortSeconds = 300", text)
        self.assertIn("OMF78_FLASH_WRAPPER_DRY_RUN_PASS=1", text)
        self.assertNotIn("F77", text)
        self.assertNotIn("f77", text)

    def test_monitor_runs_f78_stage_gate_and_detects_rx_zero(self) -> None:
        text = MONITOR.read_text(encoding="utf-8")
        self.assertIn("post_flash_f78_stage_gate.ps1", text)
        self.assertIn("PASS_F78_FLASH_2G_AND_5G_MODULE_STAGE", text)
        self.assertIn("BLOCKED_BY_FLASH_UART_RX_ZERO", text)
        self.assertIn("Test-F78FlashUartRxZero", text)
        self.assertNotIn("F77", text)
        self.assertNotIn("f77", text)

    def test_stage_gate_uses_f78_markers(self) -> None:
        text = STAGE.read_text(encoding="utf-8")
        self.assertIn("OMF78_STAGE_MODULES_BEGIN", text)
        self.assertIn("PASS_F78_2G_AND_5G_MODULE_STAGE", text)
        self.assertIn("openmitrastar.f78-stage-gate/v1", text)
        self.assertNotIn("F77", text)
        self.assertNotIn("f77", text)

    def test_auto_arm_uses_precontrol_flash_wrapper(self) -> None:
        text = ARM.read_text(encoding="utf-8")
        self.assertIn("openmitrastar.f78-auto-arm/v1", text)
        self.assertIn("flash_f78_2g_fast_5g_precontrol_stage_guard.ps1", text)
        self.assertIn("monitor_f78_flash_then_stage_gate.ps1", text)
        self.assertIn("OMF78_AUTO_ARM_DRY_RUN_PASS=1", text)
        self.assertIn("OMF78_AUTO_ARMED=1", text)
        self.assertNotIn("flash_f78_2g_fast_5g_stage_guard.ps1", text)


if __name__ == "__main__":
    unittest.main()
