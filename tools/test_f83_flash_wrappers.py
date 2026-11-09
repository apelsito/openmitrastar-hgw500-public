#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f83_5g_post_hostapd_stage_2g_mcs7.ps1"
MONITOR = ROOT / "tools/monitor_f83_flash_then_stage_gate.ps1"
STAGE = ROOT / "tools/post_flash_f83_stage_gate.ps1"
ARM = ROOT / "tools/arm_f83_flash_then_stage_gate.ps1"


class F83FlashWrapperTests(unittest.TestCase):
    def test_flash_wrapper_points_at_f83_build_and_ack(self) -> None:
        text = FLASH.read_text(encoding="ascii")
        self.assertIn(
            "q3-persistent-composite-f83-5g-post-hostapd-stage-2g-mcs7\\build",
            text,
        )
        self.assertIn(
            "OPENMITRASTAR_Q3_F83_5G_POST_HOSTAPD_STAGE_2G_MCS7_MTD4_FLASH_1E3AF819",
            text,
        )
        self.assertIn('[string]$CurrentLiveCrc32 = "20e93d1b"', text)
        self.assertIn("OMF83_FLASH_WRAPPER_DRY_RUN_PASS=1", text)
        self.assertIn("AllowInfiniteNoRxWait", text)
        self.assertIn("invalid_no_rx_abort", text)
        self.assertIn("uart_rx_zero", text)
        self.assertIn("F83 flash wrapper aborted because UART RX stayed silent", text)
        self.assertIn("external_stdout_log", text)
        self.assertNotIn("q3-persistent-composite-F83", text)
        self.assertNotIn("q3-persistent-composite-f81", text)
        self.assertNotIn("flash_f81", text)

    def test_monitor_runs_f83_stage_gate_and_detects_rx_zero(self) -> None:
        text = MONITOR.read_text(encoding="ascii")
        self.assertIn("post_flash_f83_stage_gate.ps1", text)
        self.assertIn("PASS_F83_FLASH_2G_AND_5G_POST_HOSTAPD_STAGE", text)
        self.assertIn("BLOCKED_BY_FLASH_UART_RX_ZERO", text)
        self.assertIn('"uart_rx_zero"', text)
        self.assertIn("Test-F83FlashUartRxZero", text)
        self.assertIn("external_stdout_log", text)
        self.assertIn("Diag2gMbps = 20.0", text)
        self.assertIn("-Diag2gMbps", text)
        self.assertIn("openmitrastar.f83-flash-then-stage-gate-monitor/v1", text)
        self.assertNotIn("post_flash_f81", text)
        self.assertNotIn("flash_f81", text)

    def test_stage_gate_uses_post_hostapd_markers(self) -> None:
        text = STAGE.read_text(encoding="ascii")
        self.assertIn("OMF83_STAGE_POST_HOSTAPD_BEGIN", text)
        self.assertIn("OM_RADIO5_STAGE_STOP=post-hostapd", text)
        self.assertIn("PASS_F83_2G_AND_5G_POST_HOSTAPD_STAGE", text)
        self.assertIn("openmitrastar.f83-post-hostapd-stage-gate/v1", text)
        self.assertIn("$stagePass -and $stageRc -eq 0 -and $controlEntered", text)
        self.assertNotIn("\\$controlEntered", text)

    def test_auto_arm_uses_f83_flash_and_monitor(self) -> None:
        text = ARM.read_text(encoding="ascii")
        self.assertIn("openmitrastar.f83-auto-arm/v1", text)
        self.assertIn("flash_f83_5g_post_hostapd_stage_2g_mcs7.ps1", text)
        self.assertIn("monitor_f83_flash_then_stage_gate.ps1", text)
        self.assertIn("OMF83_AUTO_ARM_DRY_RUN_PASS=1", text)
        self.assertIn("OMF83_AUTO_ARMED=1", text)
        self.assertIn("AllowInfiniteNoRxWait", text)
        self.assertIn("invalid_no_rx_abort", text)
        self.assertIn("requested_no_rx_abort_seconds", text)
        self.assertIn("max_default_no_rx_abort_seconds", text)
        self.assertIn("OM_F83_FLASH_LAUNCH_LOG", text)
        self.assertIn("flash_launch_stderr_log", text)
        self.assertIn("Diag2gMbps = 20.0", text)
        self.assertIn("-Diag2gMbps", text)
        self.assertNotIn("flash_F83_2g_fast_5g_precontrol_stage_guard.ps1", text)


if __name__ == "__main__":
    unittest.main()
