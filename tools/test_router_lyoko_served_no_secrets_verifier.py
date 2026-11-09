#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools" / "verify_router_lyoko_served_no_secrets.py"
WEB_ROOT = ROOT / "work" / "mission-state" / "router-lyoko-v0" / "rootfs" / "var" / "www"
MANIFEST = ROOT / "work" / "mission-state" / "router-lyoko-v0" / "manifest.json"


def run_verifier(base_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--manifest",
            str(MANIFEST),
            "--base-dir",
            str(base_dir),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoServedNoSecretsVerifierTests(unittest.TestCase):
    def test_accepts_current_local_web_root(self) -> None:
        proc = run_verifier(WEB_ROOT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["classification"], "READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL")
        self.assertGreaterEqual(report["payloads_scanned"], 21)
        self.assertEqual(report["findings_count"], 0)

    def test_rejects_secret_in_static_served_file_without_printing_value(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "www"
            shutil.copytree(WEB_ROOT, clone)
            (clone / "lyoko.js").write_text(
                (clone / "lyoko.js").read_text(encoding="utf-8")
                + "\nwindow.xana = { wpa_psk: 'router-lab-secret-1234' };\n",
                encoding="utf-8",
            )
            proc = run_verifier(clone)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertEqual(report["findings"][0]["key"].lower(), "wpa_psk")
            self.assertNotIn("router-lab-secret-1234", proc.stdout)

    def test_rejects_secret_in_api_response_without_printing_value(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "www"
            shutil.copytree(WEB_ROOT, clone)
            (clone / "api/lyoko-control").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "schema": "router-lyoko.control-contract/v1",
                        "COOKIE_SESSION_KEY": "router-lab-secret-1234",
                    }
                ),
                encoding="utf-8",
            )
            proc = run_verifier(clone)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            keys = {finding["key"] for finding in report["findings"]}
            self.assertIn("COOKIE_SESSION_KEY", keys)
            self.assertNotIn("router-lab-secret-1234", proc.stdout)

    def test_source_is_read_only_and_has_no_hardware_mutation_commands(self) -> None:
        source = VERIFIER.read_text(encoding="utf-8")
        self.assertIn("urllib.request.Request", source)
        self.assertIn("method=\"GET\"", source)
        self.assertIn("READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL", source)
        for forbidden in (
            "ramssh_exec.py",
            "flash_erase",
            "mtd_debug",
            "fw_setenv",
            "saveenv",
            "reboot -f",
            "COM3",
            "mode COM",
            "bootm",
            "ATGO",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
