#!/usr/bin/env python3
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_w2_tx17_ram_boot.ps1"


class Tx17RamBootTests(unittest.TestCase):
    def test_runner_is_fail_closed_and_hash_pinned(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("5a528ca78446041d7a53a0c789da8fd388f8bacc6e2286056adaa118775a1f53", text)
        self.assertIn("4332045", text)
        self.assertIn("OPENMITRASTAR_TX17_RAM_BOOT_ONLY_NO_FLASH", text)
        self.assertIn("if (-not $Execute)", text)
        self.assertIn("-AutonomousEntropy", text)
        self.assertIn('$RawText = $Raw -join "`n"', text)
        self.assertNotIn("flash_erase", text)
        self.assertNotIn("fw_setenv", text)

    def test_plan_only_does_not_open_uart_or_reboot(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX17_RAM_BOOT_PREFLIGHT_PASS=1 execute=0 flash=0", proc.stdout)
        self.assertIn('"uart_opened":  false', proc.stdout)
        self.assertIn('"reboot":  false', proc.stdout)
        self.assertIn('"flash":  false', proc.stdout)


if __name__ == "__main__":
    unittest.main()
