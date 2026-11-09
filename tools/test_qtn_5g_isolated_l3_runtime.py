#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_qtn_5g_isolated_l3_runtime.py"


class Qtn5gIsolatedL3RuntimeTests(unittest.TestCase):
    def test_reproducible_build_and_topology(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(BUILDER), "--output-dir", str(out)],
                cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual("192.168.77.1/24", manifest["network"]["wifi0"])
            self.assertFalse(manifest["network"]["wifi0_in_br0"])
            self.assertEqual(512, manifest["network"]["tqe_ring_entries"])
            self.assertTrue(manifest["reproducible"])

    def test_start_has_no_wifi0_bridge_and_has_static_address(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            subprocess.run([sys.executable, str(BUILDER), "--output-dir", str(out)], cwd=ROOT, check=True)
            start = (out / "om-radio5-start-isolated-l3").read_text()
            self.assertNotIn("brctl addif br0 wifi0", start)
            self.assertNotIn("'bridge=br0'", start)
            self.assertIn("ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up", start)
            self.assertIn("OMQTN5G_ISOLATED_L3", start)
            self.assertIn('case "$tqe_ring_entries" in 256|512)', start)
            self.assertIn("board_radio_oem_profile=1", start)
            self.assertIn("qdrv_profile=current-rc1-cf02", start)
            self.assertIn("beacon_preflight_enable=1", start)
            self.assertIn("beacon_v89_wire_enable=1", start)
            self.assertIn("openmitrastar_beacon_v89_wire_enable=1", start)
            self.assertIn("No DDR heap memory for beacon buffer", start)

    def test_stop_clears_static_ip_and_preserves_br0_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            subprocess.run([sys.executable, str(BUILDER), "--output-dir", str(out)], cwd=ROOT, check=True)
            stop = (out / "om-radio5-stop-isolated-l3").read_text()
            self.assertIn("ifconfig wifi0 0.0.0.0", stop)
            self.assertIn("eth0_2g", stop)
            self.assertNotIn("brctl delif \"$br\" wlan0", stop)


if __name__ == "__main__":
    unittest.main(verbosity=2)
