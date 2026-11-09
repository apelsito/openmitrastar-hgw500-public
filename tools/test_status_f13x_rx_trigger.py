from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/status_f13x_rx_trigger.ps1"


class StatusF13xRxTriggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_reports_trigger_monitor_serial_and_ssh(self) -> None:
        self.assertIn("OMF13X_STATUS_PORT_PRESENT", self.text)
        self.assertIn("OMF13X_STATUS_TRIGGER_STATE", self.text)
        self.assertIn("OMF13X_STATUS_MONITOR_STATE", self.text)
        self.assertIn("OMF13X_STATUS_SSH_TCP", self.text)

    def test_finds_all_f13x_profiles(self) -> None:
        self.assertIn('[ValidateSet("F133", "F134", "F135")]', self.text)
        self.assertIn("^f13x-rx-trigger-$profileLower-", self.text)
        self.assertIn("^f13x-rx-trigger-monitor-$profileLower-", self.text)

    def test_status_script_does_not_write_flash_or_uart(self) -> None:
        self.assertNotIn("-Execute", self.text)
        self.assertNotIn("SerialPort]::new", self.text)
        self.assertNotIn("Write(\"", self.text)
        self.assertNotIn("linux_safety", self.text)


if __name__ == "__main__":
    unittest.main()
