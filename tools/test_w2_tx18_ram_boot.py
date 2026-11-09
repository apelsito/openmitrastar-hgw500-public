#!/usr/bin/env python3
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_w2_tx18_ram_boot.ps1"


class Tx18RamBootTests(unittest.TestCase):
    def test_runner_is_exact_and_fail_closed(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("6a4486fa3f1e4312bee30758155d5bbbc1b732c821c9d6898f3b25f2f4164243", text)
        self.assertIn("4331946", text)
        self.assertIn("OPENMITRASTAR_TX18_RAM_BOOT_ONLY_NO_FLASH", text)
        self.assertIn("txbd_mgmt_split -ne $false", text)
        self.assertIn("MGMT_SPLIT=N", text)
        self.assertNotIn("flash_erase", text)
        self.assertNotIn("fw_setenv", text)

    def test_plan_only_does_not_touch_hardware(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER)],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX18_RAM_BOOT_PREFLIGHT_PASS=1 execute=0 flash=0", proc.stdout)
        self.assertIn('"management_split":  false', proc.stdout)
        self.assertIn('"uart_opened":  false', proc.stdout)
        self.assertIn('"reboot":  false', proc.stdout)


if __name__ == "__main__":
    unittest.main()
