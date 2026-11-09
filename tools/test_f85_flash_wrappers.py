#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f85_5g_cal_mac_prep_after_f84.ps1"
MONITOR = ROOT / "tools/monitor_f85_flash_then_stage_gate.ps1"
STAGE = ROOT / "tools/post_flash_f85_stage_gate.ps1"
ARM = ROOT / "tools/arm_f85_flash_then_stage_gate.ps1"


class F85FlashWrapperTests(unittest.TestCase):
    def test_flash_wrapper_points_at_f85_build_and_ack(self) -> None:
        text = FLASH.read_text(encoding="ascii")
        self.assertIn(
            "q3-persistent-composite-f85-5g-cal-mac-prep-after-f84\\build",
            text,
        )
        self.assertIn(
            "OPENMITRASTAR_Q3_F85_5G_CAL_MAC_PREP_AFTER_F84_MTD4_FLASH_E78CA868",
            text,
        )
        self.assertIn('[string]$CurrentLiveCrc32 = "89ac7c94"', text)
        self.assertIn("OMF85_FLASH_WRAPPER_DRY_RUN_PASS=1", text)
        self.assertIn("AllowInfiniteNoRxWait", text)
        self.assertIn("invalid_no_rx_abort", text)
        self.assertIn("uart_rx_zero", text)
        self.assertIn("F85 flash wrapper aborted because UART RX stayed silent", text)
        self.assertIn("external_stdout_log", text)
        self.assertNotIn("q3-persistent-composite-F85", text)
        self.assertNotIn("q3-persistent-composite-f81", text)
        self.assertNotIn("flash_f81", text)

    def test_monitor_runs_f85_stage_gate_and_detects_rx_zero(self) -> None:
        text = MONITOR.read_text(encoding="ascii")
        self.assertIn("post_flash_f85_stage_gate.ps1", text)
        self.assertIn("PASS_F85_FLASH_2G_AND_5G_POST_HOSTAPD_STAGE", text)
        self.assertIn("BLOCKED_BY_FLASH_UART_RX_ZERO", text)
        self.assertIn('"uart_rx_zero"', text)
        self.assertIn("Test-F85FlashUartRxZero", text)
        self.assertIn("external_stdout_log", text)
        self.assertIn("Diag2gMbps = 20.0", text)
        self.assertIn("-Diag2gMbps", text)
        self.assertIn("openmitrastar.f85-flash-then-stage-gate-monitor/v1", text)
        self.assertNotIn("post_flash_f81", text)
        self.assertNotIn("flash_f81", text)

    def test_stage_gate_uses_post_hostapd_markers(self) -> None:
        text = STAGE.read_text(encoding="ascii")
        self.assertIn("OMF85_STAGE_POST_HOSTAPD_BEGIN", text)
        self.assertIn("OM_RADIO5_STAGE_STOP=post-hostapd", text)
        self.assertIn("PASS_F85_2G_AND_5G_POST_HOSTAPD_STAGE", text)
        self.assertIn("openmitrastar.f85-post-hostapd-stage-gate/v1", text)
        self.assertIn("$stagePass -and $stageRc -eq 0 -and $controlEntered", text)
        self.assertIn("BUG:", text)
        self.assertNotIn("|BUG|", text)
        self.assertNotIn("\\$controlEntered", text)

    def test_auto_arm_uses_f85_flash_and_monitor(self) -> None:
        text = ARM.read_text(encoding="ascii")
        self.assertIn("openmitrastar.f85-auto-arm/v1", text)
        self.assertIn("flash_f85_5g_cal_mac_prep_after_f84.ps1", text)
        self.assertIn("monitor_f85_flash_then_stage_gate.ps1", text)
        self.assertIn("OMF85_AUTO_ARM_DRY_RUN_PASS=1", text)
        self.assertIn("OMF85_AUTO_ARMED=1", text)
        self.assertIn("AllowInfiniteNoRxWait", text)
        self.assertIn("invalid_no_rx_abort", text)
        self.assertIn("requested_no_rx_abort_seconds", text)
        self.assertIn("max_default_no_rx_abort_seconds", text)
        self.assertIn("OM_F85_FLASH_LAUNCH_LOG", text)
        self.assertIn("flash_launch_stderr_log", text)
        self.assertIn("Diag2gMbps = 20.0", text)
        self.assertIn("-Diag2gMbps", text)
        self.assertNotIn("flash_F85_2g_fast_5g_precontrol_stage_guard.ps1", text)


if __name__ == "__main__":
    unittest.main()



