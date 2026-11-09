#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_f66_offline_preflight.py"


class F66OfflinePreflightTests(unittest.TestCase):
    def test_preflight_passes_without_hardware_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "preflight.json"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--current-live-crc32", "26523198", "--output", str(out)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertTrue(out.is_file())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual("openmitrastar.f66-offline-preflight/v1", payload["schema"])
            self.assertEqual("PASS", payload["status"])
            self.assertFalse(payload["flash"])
            self.assertFalse(payload["router_mutations"])
            self.assertFalse(payload["opens_uart"])
            self.assertEqual(
                "021cd4896ee54db95addd3b3c4111eb811b2dcf77a69c87b28b94dd4bec4b341",
                payload["candidate"]["sha256"],
            )
            self.assertEqual("26523198", payload["current_live_crc32"])
            self.assertTrue(all(check["ok"] for check in payload["checks"]))

    def test_preflight_checks_cover_flash_contract_and_runtime_markers(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for marker in (
            "sha256sums.all_match",
            "bootbase.candidate.accepted",
            "tftp.copy.matches",
            "loader.markers",
            "current_live_crc32.known",
            "flash.wrapper.pinned_candidate",
            "hgw500_tx_reclaim_poll=1",
            "OPENMITRASTAR_Q3_F66_2G_AUTORATE_RECLAIM_MTD4_FLASH_021CD489",
            "router_mutations",
            "opens_uart",
        ):
            self.assertIn(marker, text)
        for forbidden in ("SerialPort", "ssh ", "flash_erase", "mtd_debug", "fw_setenv", "saveenv"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
