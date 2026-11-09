#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/evaluate_w2_2g_client_gate.py"


class W2ClientGateTests(unittest.TestCase):
    def run_gate(self, evidence: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(TOOL), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )

    @staticmethod
    def passing() -> dict:
        return {
            "associated": True,
            "authorized": True,
            "dhcp_lease": True,
            "dns_ok": True,
            "internet_https_ok": True,
            "bridge_eth0_wlan0": True,
            "irq28_progress": True,
            "hostapd_stable": True,
            "no_kernel_oops": True,
            "duration_seconds": 600,
            "download_mbps": 8.0,
            "upload_mbps": 8.0,
            "be_queue_max": 100,
            "disconnects": 0,
            "netdev_errors_delta": 0,
        }

    def test_pass(self) -> None:
        result = self.run_gate(self.passing())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "PASS")

    def test_rejects_old_asymmetric_result(self) -> None:
        evidence = self.passing()
        evidence.update(download_mbps=0.33, upload_mbps=9.51, be_queue_max=511)
        result = self.run_gate(evidence)
        self.assertNotEqual(result.returncode, 0)
        failures = json.loads(result.stdout)["failures"]
        self.assertIn("download_mbps", failures)
        self.assertIn("directional_ratio", failures)
        self.assertIn("be_queue_max", failures)

    def test_rejects_short_soak_or_missing_dhcp(self) -> None:
        evidence = self.passing()
        evidence.update(duration_seconds=599, dhcp_lease=False)
        result = self.run_gate(evidence)
        self.assertNotEqual(result.returncode, 0)
        failures = json.loads(result.stdout)["failures"]
        self.assertIn("duration_seconds", failures)
        self.assertIn("dhcp_lease", failures)


if __name__ == "__main__":
    unittest.main()
