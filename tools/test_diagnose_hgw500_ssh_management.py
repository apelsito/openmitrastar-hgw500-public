#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/diagnose_hgw500_ssh_management.py"
spec = importlib.util.spec_from_file_location("diag", SCRIPT)
assert spec and spec.loader
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def base_report() -> dict:
    return {
        "ping": {"ok": True},
        "tcp": {
            "22": {"open": True},
            "80": {"open": True},
            "16667": {"open": True},
        },
        "getinfo": {"ok": True, "identity_ok": True},
        "ssh_default_known_hosts": {"classification": "SSH_UNKNOWN_FAILURE", "ok": False},
        "ssh_isolated_known_hosts": {"classification": "SSH_AUTH_REJECTED_PUBLICKEY", "ok": False},
    }


class Hgw500SshManagementDiagnosticTests(unittest.TestCase):
    def test_permission_denied_with_getinfo_is_not_reboot(self) -> None:
        status, action = diag.decide(base_report())
        self.assertEqual("SSH_AUTH_REJECTED_MANAGEMENT_OK", status)
        self.assertIn("No physical reboot", action)

    def test_hostkey_stale_but_isolated_auth_ok_is_client_side(self) -> None:
        report = base_report()
        report["ssh_default_known_hosts"] = {"classification": "SSH_HOSTKEY_PROBLEM", "ok": False}
        report["ssh_isolated_known_hosts"] = {"classification": "SSH_AUTH_OK", "ok": True}
        status, action = diag.decide(report)
        self.assertEqual("SSH_OK_DEFAULT_KNOWN_HOSTS_STALE", status)
        self.assertIn("known_hosts", action)

    def test_all_management_down_is_physical_recovery_candidate(self) -> None:
        report = base_report()
        report["ping"]["ok"] = False
        report["tcp"]["22"]["open"] = False
        report["tcp"]["80"]["open"] = False
        report["tcp"]["16667"]["open"] = False
        report["getinfo"] = {"ok": False, "identity_ok": False}
        report["ssh_isolated_known_hosts"] = {"classification": "SSH_CONNECT_TIMEOUT", "ok": False}
        status, action = diag.decide(report)
        self.assertEqual("MANAGEMENT_UNREACHABLE_PHYSICAL_RECOVERY_CANDIDATE", status)
        self.assertIn("Physical power-cycle", action)

    def test_script_dry_style_does_not_mutate_router_or_default_known_hosts(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "reboot -f", "ATGO", "bootm"):
            self.assertNotIn(forbidden, source)
        self.assertIn('"default_known_hosts": False', source)
        self.assertIn("UserKnownHostsFile", source)
        self.assertIn("StrictHostKeyChecking=yes", source)
        self.assertIn("StrictHostKeyChecking=no", source)

    def test_help_runs(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("Read-only HGW-500BNA-QCv2", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
