from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/arm_f126_5g_assoc_observe_flash.ps1"
MONITOR = ROOT / "tools/monitor_f126_flash_then_assoc_only_5g.ps1"
SUPERVISOR = ROOT / "tools/start_f126_flash_then_assoc_monitor.ps1"


class F126FlashWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.monitor = MONITOR.read_text(encoding="utf-8")
        cls.supervisor = SUPERVISOR.read_text(encoding="utf-8")

    def test_wrapper_is_pinned_to_f126_candidate(self) -> None:
        self.assertIn("q3-persistent-composite-f126-5g-assoc-observe-from-f125", self.wrapper)
        self.assertIn("OPENMITRASTAR_Q3_F126_5G_ASSOC_OBSERVE_FROM_F125", self.wrapper)
        self.assertIn("87e0d43536a2d80baf8353c52919d9c7c02de595dcc70b8ddd65ee5797197089", self.wrapper)
        self.assertIn('$ExpectedBytes = "4373352"', self.wrapper)
        self.assertIn('$ExpectedCandidateCrc32 = "219ba514"', self.wrapper)
        self.assertIn('$ExpectedFullSlotCrc32 = "d690488d"', self.wrapper)

    def test_wrapper_expects_current_f124_live_slot(self) -> None:
        self.assertIn('[string]$CurrentLiveCrc32 = "001de769"', self.wrapper)

    def test_wrapper_delegates_to_existing_bootbase_flash_backend(self) -> None:
        self.assertIn("run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py", self.wrapper)
        self.assertIn("q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1", self.wrapper)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", self.wrapper)
        self.assertIn("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", self.wrapper)
        self.assertIn("[int]$BlindAtguAfterNoRxSeconds = 8", self.wrapper)
        self.assertIn("blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds", self.wrapper)

    def test_monitor_is_pinned_to_f126_and_runs_2g_first(self) -> None:
        self.assertIn("openmitrastar.f126-flash-then-5g-assoc-only-monitor/v1", self.monitor)
        self.assertIn("openmitrastar.f126-5g-assoc-only-gate/v1", self.monitor)
        self.assertIn("87e0d43536a2d80baf8353c52919d9c7c02de595dcc70b8ddd65ee5797197089", self.monitor)
        self.assertIn("f126-5g-assoc-observe-from-f125", self.monitor)
        self.assertIn("run_aelita_2g_wpa2_speed_router_probe.py", self.monitor)
        self.assertIn('[string]$TwoGTrafficDirection = "both"', self.monitor)
        self.assertIn("TWO_G_PREFLIGHT_FAIL", self.monitor)
        self.assertIn("two_g_gate_first", self.monitor)
        self.assertIn("run_qtn_5g_aelita_assoc_only.py", self.monitor)
        self.assertIn("OPENMITRASTAR_QTN_5G_AELITA_ASSOC_ONLY", self.monitor)
        self.assertIn("PASS_ASSOC_ONLY", self.monitor)

    def test_monitor_reports_zero_uart_from_log_and_blind_autobreak(self) -> None:
        self.assertIn("uart_log = $uartLogPath", self.monitor)
        self.assertIn("uart_log_bytes = $uartLogBytes", self.monitor)
        self.assertIn("blind_space_count = $blindSpaceCount", self.monitor)
        self.assertIn("$uartLogBytes -eq 0 -and $blindSpaceCount -ge 20", self.monitor)
        self.assertIn('Write-MonitorStatus "uart_rx_zero_no_flash"', self.monitor)

    def test_monitor_requires_2g_speed_threshold_for_every_requested_direction(self) -> None:
        self.assertIn("$downloadMbps", self.monitor)
        self.assertIn("$uploadMbps", self.monitor)
        self.assertIn("$requestedSpeeds", self.monitor)
        self.assertIn("$validSpeeds.Count -eq $requestedSpeeds.Count", self.monitor)
        self.assertIn("download_mbps = $downloadMbps", self.monitor)
        self.assertIn("upload_mbps = $uploadMbps", self.monitor)
        self.assertIn("router_health_gate", self.monitor)
        self.assertIn("router_health_pass = $routerHealthPass", self.monitor)
        self.assertIn("two_g_router_health_failed", self.monitor)
        self.assertIn("child_pass = $childPass", self.monitor)
        self.assertIn("two_g_preflight_child_failed", self.monitor)

    def test_monitor_does_not_use_5g_traffic_uart_or_mutating_flash_tools(self) -> None:
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
            self.assertNotIn(marker, self.monitor)

    def test_supervisor_reuses_active_f126_watcher_and_starts_monitor(self) -> None:
        self.assertIn("openmitrastar.f126-auto-arm-and-monitor/v1", self.supervisor)
        self.assertIn("arm_f126_5g_assoc_observe_flash.ps1", self.supervisor)
        self.assertIn("monitor_f126_flash_then_assoc_only_5g.ps1", self.supervisor)
        self.assertIn("$watcherAlive", self.supervisor)
        self.assertIn("if (-not $watcherAlive)", self.supervisor)
        self.assertIn("$ReplaceWatcher -and $watcherAlive", self.supervisor)
        self.assertIn("$ReplaceMonitor -and $monitorAlive", self.supervisor)
        self.assertIn("-AllowBlindAutobreak", self.supervisor)
        self.assertIn("-AllowNoRxRebootAssist", self.supervisor)
        self.assertIn("-Min2gMbps", self.supervisor)
        self.assertIn('[string]$TwoGTrafficDirection = "both"', self.supervisor)


if __name__ == "__main__":
    unittest.main()
