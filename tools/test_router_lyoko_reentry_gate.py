#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_router_lyoko_reentry.ps1"


class RouterLyokoReentryGateTests(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                *args,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    def test_plan_only_is_default_and_read_only(self) -> None:
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OMLYOKO_REENTRY_PLAN_PASS=1", result.stdout)
        self.assertIn('"mode":  "plan-only"', result.stdout)
        self.assertIn("verify_router_lyoko_live.py", result.stdout)
        self.assertIn("verify_router_lyoko_control_api.py", result.stdout)
        self.assertIn("verify_router_lyoko_static_index.py", result.stdout)
        self.assertIn("verify_router_lyoko_served_files.py", result.stdout)
        self.assertIn("verify_router_lyoko_served_no_secrets.py", result.stdout)
        self.assertIn("verify_router_lyoko_reentry_result.py", result.stdout)
        self.assertIn("/api/lyoko", result.stdout)
        self.assertIn("/api/lyoko-control", result.stdout)
        self.assertIn("/lyoko-data/index.json", result.stdout)
        self.assertIn("/lyoko.html", result.stdout)
        self.assertIn("/lyoko.css", result.stdout)
        self.assertIn("/lyoko.js", result.stdout)
        self.assertIn("manifest.json", result.stdout)
        self.assertIn('"uart_opened":  false', result.stdout)
        self.assertIn('"ssh_command":  false', result.stdout)
        self.assertIn('"flash":  false', result.stdout)
        self.assertIn("OPENMITRASTAR_LYOKO_REENTRY_READONLY", result.stdout)

    def test_execute_requires_ack(self) -> None:
        result = self.run_script("-Execute")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("OPENMITRASTAR_LYOKO_REENTRY_READONLY", result.stderr)

    def test_source_is_http_get_verifier_only(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_router_lyoko_live.py", source)
        self.assertIn("verify_router_lyoko_control_api.py", source)
        self.assertIn("verify_router_lyoko_static_index.py", source)
        self.assertIn("verify_router_lyoko_served_files.py", source)
        self.assertIn("verify_router_lyoko_served_no_secrets.py", source)
        self.assertIn("verify_router_lyoko_reentry_result.py", source)
        self.assertIn("--require-kernel-510", source)
        self.assertIn("--require-bridge-up", source)
        self.assertIn("--require-ssh-running", source)
        self.assertIn("--require-management-path", source)
        self.assertIn("--require-recovery-guards", source)
        self.assertIn("/api/lyoko-control", source)
        self.assertIn("control_verifier_ok", source)
        self.assertIn("/lyoko-data/index.json", source)
        self.assertIn("static_index_verifier_ok", source)
        self.assertIn("/lyoko.html", source)
        self.assertIn("/lyoko.css", source)
        self.assertIn("/lyoko.js", source)
        self.assertIn("served_files_verifier_ok", source)
        self.assertIn("served_no_secrets_verifier_ok", source)
        self.assertIn("result_verifier_ok", source)
        self.assertIn("lyoko-served-no-secrets-verifier.stdout.json", source)
        self.assertIn("lyoko-reentry-result-verifier.stdout.json", source)
        self.assertIn("AllowedPrefix", source)
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
            "om-radio5-start",
            "run_qtn_w3_tx7_client_traffic",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
