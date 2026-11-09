#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_qtn_5g_txpath_trace_runtime.py"


class Qtn5gTxPathDiscriminantTests(unittest.TestCase):
    def test_build_is_reproducible_and_trace_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = subprocess.run([sys.executable, str(BUILDER), "--output-dir", str(out)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(["bounded logging only"], manifest["behavior_changes"])
            self.assertFalse(manifest["fwt_ctrl"])
            self.assertFalse(manifest["ioss"])
            self.assertFalse(manifest["flash"])
            self.assertEqual(6, len(manifest["markers"]))

    def test_start_changes_only_qdrv_trace_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            subprocess.run([sys.executable, str(BUILDER), "--output-dir", str(out)], cwd=ROOT, check=True)
            start = (out / "om-radio5-start-txpath-trace").read_text()
            self.assertEqual(3, start.count("openmitrastar_tx_path_trace_enable=1"))
            self.assertNotIn("fwt_ctrl.ko", start)
            self.assertIn("192.168.77.1", start)
            self.assertNotIn("brctl addif br0 wifi0", start)

    def test_expected_marker_order(self) -> None:
        manifest = json.loads((ROOT / "outputs/kernel-port/quantenna-5g-txpath-discriminant-20260823/manifest.json").read_text())
        self.assertEqual(
            ["enqueue", "hardstart", "desc-ready", "mailbox-enter", "mailbox-published", "txdone"],
            manifest["markers"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
