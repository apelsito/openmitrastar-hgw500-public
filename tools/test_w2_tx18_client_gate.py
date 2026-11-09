#!/usr/bin/env python3
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_w2_tx18_client_gate.ps1"


class Tx18ClientGateTests(unittest.TestCase):
    def test_gate_is_exact_readonly_and_chains_traffic_capture(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("6a4486fa3f1e4312bee30758155d5bbbc1b732c821c9d6898f3b25f2f4164243", text)
        self.assertIn("4331946", text)
        self.assertIn("wait_w2_2g_client.py", text)
        self.assertIn("--require-authorized", text)
        self.assertIn("run_w2_2g_candidate_gate.ps1", text)
        self.assertIn("MGMT_SPLIT=N", text)
        self.assertIn("uart_opened = $false", text)
        self.assertIn("reboot = $false", text)
        self.assertNotIn("flash_erase", text)
        self.assertNotIn("fw_setenv", text)

    def test_plan_only_does_not_touch_router(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER)],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX18_CLIENT_GATE_PLAN_PASS=1 execute=0 flash=0", proc.stdout)
        self.assertIn('"execution_requested":  false', proc.stdout)
        self.assertIn('"reboot":  false', proc.stdout)
        self.assertIn('"flash":  false', proc.stdout)


if __name__ == "__main__":
    unittest.main()
