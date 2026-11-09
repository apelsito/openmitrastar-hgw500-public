#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/monitor_qtn_w3_5g_client.py"


class Qtn5gClientMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_monitor_is_read_only(self):
        lowered = self.text.lower()
        for forbidden in ("set_channel", "set_bw", "rf_enable", "flash_erase", "mtd write", "saveenv"):
            self.assertNotIn(forbidden, lowered)
        self.assertIn("read_only=1", self.text)

    def test_requires_association_and_bidirectional_progress(self):
        self.assertIn('current["assoc"] > 0', self.text)
        for counter in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets"):
            self.assertIn(f'current["{counter}"] > baseline["{counter}"]', self.text)

    def test_does_not_claim_internet_or_f3(self):
        self.assertIn("internet_speedtest=UNVERIFIED F3=0", self.text)

    def test_dry_run(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--autopilot-log", "unused", "--dry-run"],
            cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("W3_QTN_5G_CLIENT_MONITOR_DRY_RUN_PASS=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
