#!/usr/bin/env python3

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/status_f70_f73_goal.ps1"


class StatusF70F73GoalTests(unittest.TestCase):
    def test_status_script_is_read_only_for_uart_and_flash(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("[IO.Ports.SerialPort]", text)
        self.assertNotRegex(text, re.compile(r"\bspi_flash\b|\bATGU\b|\bbootm\b"))
        self.assertNotRegex(text, re.compile(r"recover_flash_f7[03].*\\.ps1"))

    def test_status_script_keeps_gateway_as_non_target(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("$GatewayHost = \"192.168.1.1\"", text)
        self.assertIn("gateway_non_target", text)
        self.assertIn("WAIT_PHYSICAL_UART_RX_OR_ROUTER_POWER_CYCLE", text)

    def test_status_script_reports_watchers_and_uart_bytes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for needle in (
            "$F70ProcessId = 14084",
            "$ChainProcessId = 20192",
            "f70_restore",
            "f70_to_f73_chain",
            "uart",
            "rx_seen",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
