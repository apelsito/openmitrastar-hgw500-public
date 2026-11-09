#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_5g_visibility_probe.py"


class Qtn5gVisibilityProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_dry_run_documents_live_only_contract(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        marker = "OMQTN5G_VISIBILITY_PROBE_DRY_RUN_PASS=1"
        self.assertIn(marker, proc.stdout)
        payload = json.loads(proc.stdout[:proc.stdout.index(marker)])
        self.assertEqual("AELITA@192.168.1.63", payload["oracle"])
        self.assertEqual("root@192.168.1.90", payload["router"])
        self.assertFalse(payload["flash"])
        self.assertFalse(payload["reboot"])
        self.assertFalse(payload["module_loads"])
        self.assertFalse(payload["mtd_writes"])

    def test_execution_requires_exact_ack_and_restores_hostapd(self) -> None:
        self.assertIn("ACK = \"OPENMITRASTAR_QTN5G_VISIBILITY_PROBE_LIVE\"", self.source)
        self.assertIn("Require --ack", self.source)
        self.assertIn("finally:", self.source)
        self.assertIn("RESTORE_SECURE_HOSTAPD", self.source)
        self.assertIn("PREPARE_SECURE_RESTORE_HOSTAPD", self.source)
        self.assertIn("hostapd-secure-restore.conf", self.source)
        self.assertIn("router_script(", self.source)
        self.assertIn("OMQTN5G_RESTORE_SECURE_READY", self.source)
        self.assertIn("OMQTN5G_PREPARE_RESTORE_READY", self.source)
        self.assertIn("qtn_5g_isolated_open_diag_live.sh", self.source)
        self.assertNotIn("/bin/ash -s --", self.source)
        helper = (ROOT / "tools/qtn_5g_isolated_open_diag_live.sh").read_text(encoding="utf-8")
        self.assertIn("iwconfig-qtn wifi0 essid", helper)
        self.assertIn("iwconfig-qtn wifi0 channel 36", helper)
        self.assertIn("iwpriv-qtn wifi0 mode 11ac80Edge+", helper)

    def test_forbids_persistent_or_module_mutations(self) -> None:
        for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "reboot_boot_ramssh", "insmod ", "rmmod "):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
