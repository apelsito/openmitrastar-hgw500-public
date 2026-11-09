#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_router_lyoko_no_secrets.py"


def run_scan(web_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--web-root", str(web_root)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoNoSecretsTests(unittest.TestCase):
    def test_current_overlay_passes(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["findings_count"], 0)
        self.assertEqual(report["classification"], "READONLY-WEB-SECRET-SCAN-NO-CONTROL")

    def test_policy_text_false_and_blocked_is_not_a_secret(self):
        with tempfile.TemporaryDirectory() as td:
            web = Path(td)
            (web / "policy.json").write_text(
                json.dumps(
                    {
                        "contains_secrets": False,
                        "secret_exfiltration": False,
                        "secret_rendering": "blocked",
                        "notes": ["no secrets are rendered or logged"],
                    }
                ),
                encoding="utf-8",
            )
            proc = run_scan(web)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(json.loads(proc.stdout)["ok"])

    def test_rejects_private_key_marker_without_printing_key_body(self):
        with tempfile.TemporaryDirectory() as td:
            web = Path(td)
            (web / "bad.pem").write_text(
                "-----BEGIN OPENSSH PRIVATE KEY-----\n"
                "definitely-do-not-print-this-body\n"
                "-----END OPENSSH PRIVATE KEY-----\n",
                encoding="utf-8",
            )
            proc = run_scan(web)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertEqual(report["findings"][0]["kind"], "pem_secret_material")
            self.assertNotIn("definitely-do-not-print-this-body", proc.stdout)

    def test_rejects_concrete_router_secret_assignment_without_printing_value(self):
        with tempfile.TemporaryDirectory() as td:
            web = Path(td)
            (web / "bad.js").write_text(
                "window.config = { login_password: 'router-lab-secret-1234' };\n",
                encoding="utf-8",
            )
            proc = run_scan(web)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertEqual(report["findings"][0]["kind"], "secret_assignment")
            self.assertEqual(report["findings"][0]["key"], "login_password")
            self.assertNotIn("router-lab-secret-1234", proc.stdout)

    def test_allows_redacted_or_placeholder_secret_fields(self):
        with tempfile.TemporaryDirectory() as td:
            web = Path(td)
            (web / "ok.json").write_text(
                json.dumps(
                    {
                        "password": "REDACTED",
                        "wpa_psk": "<redacted>",
                        "SECRET_ACCESS_KEY": "${SECRET_ACCESS_KEY}",
                    }
                ),
                encoding="utf-8",
            )
            proc = run_scan(web)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
