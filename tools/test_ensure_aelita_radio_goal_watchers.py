#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/ensure_aelita_radio_goal_watchers.ps1"


class EnsureAelitaRadioGoalWatchersTests(unittest.TestCase):
    def test_watchdog_ensures_f83_and_router_runtime_watchers(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("openmitrastar.aelita-radio-goal-watchdog/v1", text)
        self.assertIn("Ensure-F83AutoArm", text)
        self.assertIn("Ensure-RouterSshMonitor", text)
        self.assertIn("arm_f83_flash_then_stage_gate.ps1", text)
        self.assertIn("monitor_router_ssh_then_radio_gate.ps1", text)
        self.assertIn("[switch]$Run5gProbe", text)
        self.assertIn("[switch]$DryRun", text)
        self.assertIn("[switch]$Once", text)
        self.assertIn("OMAELITA_RADIO_WATCHDOG_ONCE=1", text)
        self.assertIn("-Run5gProbe", text)
        self.assertIn("-FiveGProfile", text)
        self.assertIn("-Diag2gMbps", text)
        self.assertIn("run_5g_probe", text)
        self.assertIn("Get-ActiveFlashOwnerFromStatus", text)
        self.assertIn('@("f83", "f78", "f77", "f76")', text)
        self.assertIn("blocked_by_active_$($name)_flash", text)

    def test_watchdog_uses_gated_f83_flash_and_discovery_snapshots(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("OPENMITRASTAR_Q3_F83_5G_POST_HOSTAPD_STAGE_2G_MCS7_MTD4_FLASH_1E3AF819", text)
        self.assertIn("f83-auto-arm-watchdog", text)
        self.assertIn("-NoRxAbortSeconds", text)
        self.assertIn("-MonitorTimeoutSeconds", text)
        self.assertIn("would_start", text)
        self.assertIn("status_aelita_radio_goal.ps1", text)
        self.assertIn("discover_openmitrastar_network.ps1", text)
        self.assertIn("latest-radio-status.json", text)
        self.assertIn("latest-network-discovery.json", text)

    def test_watchdog_is_non_destructive_and_avoids_duplicate_processes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("already_running", text)
        self.assertIn("COM3 is already owned by active $name flash watcher", text)
        for forbidden in ("Remove-Item", "Stop-Process", "git reset", "saveenv"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
