#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = ROOT / "tools/qtn_w3_hbm_only_remote.sh"
RUNNER = ROOT / "tools/run_qtn_w3_hbm_only.ps1"
GATE = ROOT / "work/mission-state/w3-offline/W3_HBM_ONLY_GATE.env"
APPROVED_GATE = ROOT / "work/mission-state/w3-offline/W3_HBM_ONLY_GATE.approved.env"


class HbmOnlyTests(unittest.TestCase):
    def test_gate_defaults_closed_and_pair_is_signed(self) -> None:
        text = GATE.read_text(encoding="utf-8")
        self.assertIn("W3_HBM_ONLY_APPROVED=0", text)
        self.assertIn("W3_PAIR_APPROVED=1", text)
        self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0", text)
        approved = APPROVED_GATE.read_text(encoding="utf-8")
        self.assertIn("W3_HBM_ONLY_APPROVED=0", approved)
        self.assertIn("W3_PAIR_APPROVED=1", approved)
        self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0", approved)

    def test_remote_has_exactly_one_mmio_active_insmod(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        active = re.findall(r"^insmod .*?(hbm|switch_tqe|qdrv|wlan|gpio|temp_sens|temp_sensor|fwt_ctrl)\.ko", text, re.M)
        self.assertEqual(active, ["hbm"])
        self.assertIn("rmmod hbm", text)
        self.assertIn("W3_HBM_ONLY_PASS", text)

    def test_runner_pins_watchdog_and_uart_recovery(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("5e6dd1b4a7f19e29219287f5a53b9be37722666690f019cfd75daef3e9d96358", text)
        self.assertIn("OMWDT stage=(armed|pet first=1)", text)
        self.assertIn("capture_topaz_uart.ps1", text)
        self.assertIn("uart_sysrq_reboot.ps1", text)
        self.assertIn("W3_HBM_ONLY_GATE.approved.env", text)
        self.assertNotRegex(text, re.compile(r"\b(?:flash_erase|nandwrite|mtd_debug|ubiformat)\b"))

    def test_powershell_parser_and_dry_run(self) -> None:
        parser = subprocess.run(
            ["pwsh.exe", "-NoProfile", "-Command", f"[void][scriptblock]::Create((Get-Content -Raw '{RUNNER}'))"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(parser.returncode, 0, parser.stderr)
        dry = subprocess.run(
            ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER)],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("W3_HBM_ONLY_DRY_RUN_PASS=1", dry.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
