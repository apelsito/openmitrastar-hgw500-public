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
API = ROOT / "work/mission-state/router-lyoko-v0/rootfs/var/www/api/lyoko-control"
VERIFIER = ROOT / "tools/verify_router_lyoko_control_api.py"
DATA_DIR = "/workspace/user-home/Desktop/MitraStar/work/mission-state/router-lyoko-v0/rootfs/var/www/lyoko-data"


def run_api(method: str = "GET") -> subprocess.CompletedProcess[str]:
    cmd = (
        "cd /workspace/user-home/Desktop/MitraStar && "
        f"REQUEST_METHOD={method} LYOKO_DATA_DIR={DATA_DIR} "
        "sh work/mission-state/router-lyoko-v0/rootfs/var/www/api/lyoko-control | "
        "sed '1,/^$/d'"
    )
    return subprocess.run(
        ["wsl.exe", "-e", "sh", "-lc", cmd],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_verifier(payload: dict) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "control.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--input-json", str(path)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


class RouterLyokoControlApiTests(unittest.TestCase):
    def test_shell_syntax_and_get_contract(self):
        if not shutil.which("wsl.exe"):
            self.skipTest("WSL unavailable")
        syntax = subprocess.run(
            ["wsl.exe", "-e", "sh", "-lc", "cd /workspace/user-home/Desktop/MitraStar && sh -n work/mission-state/router-lyoko-v0/rootfs/var/www/api/lyoko-control"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stdout + syntax.stderr)
        proc = run_api()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "observe_only")
        self.assertFalse(payload["request"]["executes"])
        self.assertFalse(payload["request"]["writes_device"])
        self.assertTrue(payload["policy_snapshot"]["control_policy"]["present"])
        self.assertTrue(payload["policy_snapshot"]["event_taxonomy"]["present"])
        self.assertFalse(payload["guards"]["device_write"])
        for key in (
            "control_policy",
            "event_taxonomy",
            "safe_mode",
            "goal_audit",
            "aelita_dialogue",
            "aelita_memory",
            "evidence_bindings",
            "telemetry_contract",
        ):
            self.assertTrue(payload["policy_snapshot"][key]["present"], key)
            self.assertGreater(payload["policy_snapshot"][key]["bytes"], 0, key)

    def test_non_get_is_refused_without_execution(self):
        if not shutil.which("wsl.exe"):
            self.skipTest("WSL unavailable")
        proc = run_api(method="POST")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["request"]["status"], "refused_non_get")
        self.assertFalse(payload["request"]["executes"])
        self.assertFalse(payload["request"]["writes_device"])

    def test_verifier_accepts_api_payload(self):
        if not shutil.which("wsl.exe"):
            self.skipTest("WSL unavailable")
        payload = json.loads(run_api().stdout)
        proc = run_verifier(payload)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])

    def test_verifier_rejects_write_claim(self):
        payload = json.loads(run_api().stdout) if shutil.which("wsl.exe") else {
            "schema": "router-lyoko.control-contract/v1",
            "classification": "FAIL-CLOSED-OBSERVE-ONLY-NO-DEVICE-WRITE",
            "mode": "observe_only",
            "request": {"executes": False, "writes_device": False},
            "persona": {"name": "Aelita"},
            "policy_snapshot": {
                "control_policy": {"present": True, "bytes": 1},
                "event_taxonomy": {"present": True, "bytes": 1},
                "safe_mode": {"present": True, "bytes": 1},
                "goal_audit": {"present": True, "bytes": 1},
                "aelita_dialogue": {"present": True, "bytes": 1},
                "aelita_memory": {"present": True, "bytes": 1},
                "evidence_bindings": {"present": True, "bytes": 1},
                "telemetry_contract": {"present": True, "bytes": 1},
            },
            "current_allowed_actions": [{"id": "observe", "writes_device": False}],
            "blocked_action_classes": sorted([
                "flash_promotion",
                "boot_environment_change",
                "mtd_write",
                "module_mutation",
                "radio_mutation",
                "network_change",
                "secret_rendering",
            ]),
            "guards": {
                "dashboard_executes_commands": False,
                "device_write": False,
                "flash_write": False,
                "bootenv_write": False,
                "mtd_write": False,
                "module_mutation": False,
                "network_reconfigure": False,
                "radio_control": False,
            },
        }
        payload["request"]["writes_device"] = True
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("request.no_write", failing)

    def test_verifier_rejects_missing_static_contract_snapshot(self):
        payload = json.loads(run_api().stdout) if shutil.which("wsl.exe") else {
            "schema": "router-lyoko.control-contract/v1",
            "classification": "FAIL-CLOSED-OBSERVE-ONLY-NO-DEVICE-WRITE",
            "mode": "observe_only",
            "request": {"executes": False, "writes_device": False},
            "persona": {"name": "Aelita"},
            "policy_snapshot": {
                "control_policy": {"present": True, "bytes": 1},
                "event_taxonomy": {"present": True, "bytes": 1},
                "safe_mode": {"present": True, "bytes": 1},
                "goal_audit": {"present": True, "bytes": 1},
                "aelita_dialogue": {"present": True, "bytes": 1},
                "aelita_memory": {"present": True, "bytes": 1},
                "evidence_bindings": {"present": True, "bytes": 1},
                "telemetry_contract": {"present": True, "bytes": 1},
            },
            "current_allowed_actions": [{"id": "observe", "writes_device": False}],
            "blocked_action_classes": sorted([
                "flash_promotion",
                "boot_environment_change",
                "mtd_write",
                "module_mutation",
                "radio_mutation",
                "network_change",
                "secret_rendering",
            ]),
            "guards": {
                "dashboard_executes_commands": False,
                "device_write": False,
                "flash_write": False,
                "bootenv_write": False,
                "mtd_write": False,
                "module_mutation": False,
                "network_reconfigure": False,
                "radio_control": False,
            },
        }
        payload["policy_snapshot"]["aelita_memory"]["present"] = False
        payload["policy_snapshot"]["aelita_memory"]["bytes"] = 0
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("policy_snapshot.aelita_memory.present", failing)
        self.assertIn("policy_snapshot.aelita_memory.bytes", failing)

    def test_verifier_rejects_refused_non_get_payload(self):
        payload = json.loads(run_api(method="POST").stdout) if shutil.which("wsl.exe") else {
            "ok": False,
            "schema": "router-lyoko.control-contract/v1",
            "classification": "FAIL-CLOSED-OBSERVE-ONLY-NO-DEVICE-WRITE",
            "mode": "observe_only",
            "request": {"status": "refused_non_get", "executes": False, "writes_device": False},
            "persona": {"name": "Aelita"},
            "policy_snapshot": {
                "control_policy": {"present": True, "bytes": 1},
                "event_taxonomy": {"present": True, "bytes": 1},
                "safe_mode": {"present": True, "bytes": 1},
                "goal_audit": {"present": True, "bytes": 1},
                "aelita_dialogue": {"present": True, "bytes": 1},
                "aelita_memory": {"present": True, "bytes": 1},
                "evidence_bindings": {"present": True, "bytes": 1},
                "telemetry_contract": {"present": True, "bytes": 1},
            },
            "current_allowed_actions": [{"id": "observe", "writes_device": False}],
            "blocked_action_classes": sorted([
                "flash_promotion",
                "boot_environment_change",
                "mtd_write",
                "module_mutation",
                "radio_mutation",
                "network_change",
                "secret_rendering",
            ]),
            "guards": {
                "dashboard_executes_commands": False,
                "device_write": False,
                "flash_write": False,
                "bootenv_write": False,
                "mtd_write": False,
                "module_mutation": False,
                "network_reconfigure": False,
                "radio_control": False,
            },
        }
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("ok.true", failing)
        self.assertIn("request.status.described", failing)


if __name__ == "__main__":
    unittest.main()
