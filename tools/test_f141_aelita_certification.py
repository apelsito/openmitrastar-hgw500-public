#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_f141_5g_aelita_certification.py"
WATCHER = ROOT / "tools/watch_f141_aelita_5g_certification.ps1"


class F141AelitaCertificationTests(unittest.TestCase):
    def test_runner_is_pinned_to_f141_and_never_flashes(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("OMF141_AELITA_PREFLIGHT_PASS", text)
        self.assertIn("Tx-Power[:=]21 dBm", text)
        self.assertIn("EXPECTED_WLAN_SHA", text)
        self.assertIn("EXPECTED_HOSTAPD_SHA", text)
        self.assertIn('"router_flash": False', text)
        self.assertNotIn("om-radio5-stop", text)
        self.assertNotIn("om-radio5-start", text)

    def test_watcher_waits_for_both_hosts_and_runs_once(self) -> None:
        text = WATCHER.read_text(encoding="utf-8")
        self.assertIn('Test-Tcp "192.168.1.90" 22', text)
        self.assertIn('Test-Tcp "192.168.1.63" 22', text)
        self.assertIn("run_f141_5g_aelita_certification.py", text)
        self.assertIn("router_mutations = $false", text)
        self.assertNotIn("while ($true)", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
