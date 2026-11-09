from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/arm_f125_5g_assoc_window_guard_flash.ps1"
MONITOR = ROOT / "tools/monitor_f125_flash_then_assoc_only_5g.ps1"


class F125FlashWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WRAPPER.read_text(encoding="utf-8")

    def test_wrapper_is_pinned_to_f125_candidate(self) -> None:
        self.assertIn("q3-persistent-composite-f125-5g-assoc-window-guard-from-f124", self.text)
        self.assertIn("OPENMITRASTAR_Q3_F125_5G_ASSOC_WINDOW_GUARD_FROM_F124", self.text)
        self.assertIn("d7118a035628b612deba33ea9b8fa43e52da6faf9dbd07aecb26f91789ae370e", self.text)
        self.assertIn('$ExpectedBytes = "4373358"', self.text)
        self.assertIn('$ExpectedCandidateCrc32 = "51dde9e9"', self.text)
        self.assertIn('$ExpectedFullSlotCrc32 = "b681ae75"', self.text)

    def test_wrapper_expects_current_f124_live_slot(self) -> None:
        self.assertIn('[string]$CurrentLiveCrc32 = "001de769"', self.text)

    def test_wrapper_delegates_to_bootbase_autoboot_flash_backend(self) -> None:
        self.assertIn("run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py", self.text)
        self.assertIn("q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1", self.text)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", self.text)
        self.assertIn("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", self.text)
        self.assertIn("[int]$BlindAtguAfterNoRxSeconds = 8", self.text)
        self.assertIn("blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds", self.text)
        self.assertIn('"-BlindAtguAfterNoRxSeconds", "$BlindAtguAfterNoRxSeconds"', self.text)

    def test_f125_monitor_runs_only_5g_assoc_gate_after_flash_or_ssh(self) -> None:
        text = MONITOR.read_text(encoding="utf-8")
        self.assertIn("openmitrastar.f125-flash-then-5g-assoc-only-monitor/v1", text)
        self.assertIn("d7118a035628b612deba33ea9b8fa43e52da6faf9dbd07aecb26f91789ae370e", text)
        self.assertIn("Test-TcpPort $HostAddress 22", text)
        self.assertIn("OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_PASS=1", text)
        self.assertIn("run_qtn_5g_aelita_assoc_only.py", text)
        self.assertIn("OPENMITRASTAR_QTN_5G_AELITA_ASSOC_ONLY", text)
        self.assertIn("/usr/sbin/om-radio5-start", text)
        self.assertIn("PASS_ASSOC_ONLY", text)
        self.assertIn("run_aelita_2g_wpa2_speed_router_probe.py", text)
        self.assertIn("TWO_G_PREFLIGHT_FAIL", text)
        self.assertIn("two_g_gate_first", text)
        self.assertIn("router_flash_writes = $false", text)
        self.assertIn("serial_uart = $false", text)
        self.assertIn("five_g_l3_traffic = $false", text)

    def test_f125_monitor_does_not_use_5g_traffic_uart_or_mutating_flash_tools(self) -> None:
        text = MONITOR.read_text(encoding="utf-8")
        forbidden = [
            "run_qtn_5g_aelita_one_shot.py",
            "curl",
            "iperf",
            "ping ",
            "Test-Connection",
            "SerialPort",
            "/dev/mtd",
            "mtd_debug",
            "flashcp",
            "spi_flash erase",
            "spi_flash write",
            "fw_setenv",
            "bootenv",
            "qtnboot",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
