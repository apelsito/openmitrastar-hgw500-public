#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f87_5g_bounded_default_after_f86.ps1"
MONITOR = ROOT / "tools/monitor_f87_flash_then_stage_gate.ps1"
STAGE = ROOT / "tools/post_flash_f87_stage_gate.ps1"
ARM = ROOT / "tools/arm_f87_flash_then_stage_gate.ps1"


class F87FlashWrapperTests(unittest.TestCase):
    def test_flash_wrapper_points_at_f87_build_and_ack(self) -> None:
        text = FLASH.read_text(encoding="ascii")
        self.assertIn(
            "q3-persistent-composite-f87-5g-bounded-default-after-f86\\build",
            text,
        )
        self.assertIn(
            "OPENMITRASTAR_Q3_F87_5G_BOUNDED_DEFAULT_AFTER_F86_MTD4_FLASH_AC602574",
            text,
        )
        self.assertIn('[string]$CurrentLiveCrc32 = "7d96fe19"', text)
        self.assertIn("OMF87_FLASH_WRAPPER_DRY_RUN_PASS=1", text)
        self.assertIn("Get-Command Get-FileHash", text)
        self.assertIn("Security.Cryptography.SHA256", text)
        self.assertNotIn("q3-persistent-composite-f87-5g-bounded-default-after-f87", text)
        self.assertNotIn("B0EB5E8F", text)
        self.assertNotIn("6c36b263", text)

    def test_stage_gate_validates_f87_bounded_default(self) -> None:
        text = STAGE.read_text(encoding="ascii")
        self.assertIn("OMF87_STAGE_POST_HOSTAPD_BEGIN", text)
        self.assertIn("/usr/sbin/om-radio5-start", text)
        self.assertNotIn("OM_RADIO5_STAGE_STOP=post-hostapd /usr/sbin/om-radio5-start", text)
        self.assertIn("OMRADIO5_BOUNDED_DEFAULT stage=post-hostapd", text)
        self.assertIn("bounded_default_marker", text)
        self.assertIn("PASS_F87_2G_AND_5G_POST_HOSTAPD_STAGE", text)
        self.assertIn("Resolve-PowerShellHost", text)

    def test_monitor_runs_f87_stage_gate_and_detects_rx_zero(self) -> None:
        text = MONITOR.read_text(encoding="ascii")
        self.assertIn("post_flash_f87_stage_gate.ps1", text)
        self.assertIn("PASS_F87_FLASH_2G_AND_5G_POST_HOSTAPD_STAGE", text)
        self.assertIn("BLOCKED_BY_FLASH_UART_RX_ZERO", text)
        self.assertIn("Test-F87FlashUartRxZero", text)
        self.assertIn("Resolve-PowerShellHost", text)
        self.assertNotIn("post_flash_f85", text)

    def test_auto_arm_uses_f87_flash_monitor_and_pwsh(self) -> None:
        text = ARM.read_text(encoding="ascii")
        self.assertIn("openmitrastar.f87-auto-arm/v1", text)
        self.assertIn("flash_f87_5g_bounded_default_after_f86.ps1", text)
        self.assertIn("monitor_f87_flash_then_stage_gate.ps1", text)
        self.assertIn("OMF87_AUTO_ARM_DRY_RUN_PASS=1", text)
        self.assertIn("OMF87_AUTO_ARMED=1", text)
        self.assertIn("Resolve-PowerShellHost", text)
        self.assertNotIn("flash_f87_5g_cal_mac_prep_after_f84.ps1", text)


if __name__ == "__main__":
    unittest.main()
