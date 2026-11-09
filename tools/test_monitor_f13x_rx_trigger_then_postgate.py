from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/monitor_f13x_rx_trigger_then_postgate.ps1"


class MonitorF13xRxTriggerThenPostgateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_watches_f13x_trigger_status(self) -> None:
        self.assertIn("openmitrastar.f13x-rx-trigger-postgate-monitor/v1", self.text)
        self.assertIn("Find-LatestTriggerStatus", self.text)
        self.assertIn("flash_pass", self.text)
        self.assertIn("trigger_timeout_no_rx", self.text)

    def test_runs_post_flash_gate_only_after_flash_pass(self) -> None:
        flash_pass_index = self.text.index('if ($state -eq "flash_pass")')
        gate_index = self.text.index("post_flash_f13x_radio_gate.ps1")
        self.assertGreater(gate_index, flash_pass_index)
        self.assertIn("-RunRadio5Start", self.text)
        self.assertIn("-StopRadio5First", self.text)

    def test_runs_readonly_gate_if_ssh_recovers_before_flash(self) -> None:
        self.assertIn("Test-TcpQuick", self.text)
        self.assertIn("running_ssh_recovered_readonly_gate", self.text)
        self.assertIn("PASS_SSH_RECOVERED_READ_ONLY_BASELINE", self.text)
        self.assertIn("ssh_recovered_before_flash_pass", self.text)

    def test_monitor_itself_does_not_flash_or_touch_uart(self) -> None:
        self.assertIn("flashes = $false", self.text)
        self.assertIn("touches_uart = $false", self.text)
        self.assertNotIn("linux_safety", self.text)
        self.assertNotIn("mtd3", self.text)


if __name__ == "__main__":
    unittest.main()
