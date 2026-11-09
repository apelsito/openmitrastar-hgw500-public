#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/capture_topaz_uart_resilient.ps1"


class ResilientUartCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_powershell_parses(self) -> None:
        escaped = str(SCRIPT).replace("'", "''")
        command = (
            "$e=$null;$t=$null;"
            f"[Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)|Out-Null;"
            "if($e.Count){$e|ForEach-Object{$_.ToString()};exit 1}"
        )
        proc = subprocess.run(
            ["pwsh.exe", "-NoProfile", "-Command", command], cwd=ROOT,
            text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_is_receive_only_and_does_not_toggle_control_lines(self) -> None:
        self.assertIn("$instance.DtrEnable = $false", self.source)
        self.assertIn("$instance.RtsEnable = $false", self.source)
        self.assertNotRegex(self.source, re.compile(r"\$serial\.Write(?:Line)?\s*\("))

    def test_pins_identity_and_reconnects(self) -> None:
        for marker in (
            "ExpectedPnpDeviceId",
            "Get-PnpDevice -Class Ports -PresentOnly",
            "Find-ByPnp",
            "Open-PinnedSerial",
            "stage=$Stage",
            "'port-lost'",
            "'reconnected'",
        ):
            self.assertIn(marker, self.source)

    def test_has_exclusive_mutex_and_atomic_status(self) -> None:
        self.assertIn("[Threading.Mutex]::new", self.source)
        self.assertIn("WaitOne(0)", self.source)
        self.assertIn("capture-status.json", self.source)
        self.assertIn("Move-Item -LiteralPath $temporary -Destination $statusPath -Force", self.source)
        self.assertIn("uart-events.jsonl", self.source)

    def test_does_not_contain_router_mutations(self) -> None:
        for forbidden in (
            "flash_erase", "mtd_debug", "fw_setenv", "nandwrite", "ubiformat",
            "reboot", "bootm", "tftpboot", "ramssh_exec",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
