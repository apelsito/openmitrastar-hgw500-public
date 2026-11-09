#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/validate_router_lyoko_safe_mode.py"
SAFE_MODE = ROOT / "work/mission-state/router-lyoko-v0/safe-mode.json"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoSafeModeTests(unittest.TestCase):
    def test_safe_mode_contract_validates(self):
        proc = run_validator()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["mode"], "observe_only")
        self.assertEqual(report["ack_required"], "OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY")

    def test_rejects_missing_ack(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SAFE_MODE.read_text(encoding="utf-8"))
            mutated["ack_required"] = "WRONG"
            path = Path(td) / "safe-mode.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--safe-mode", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("ack_required", proc.stderr)

    def test_rejects_dashboard_execution(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SAFE_MODE.read_text(encoding="utf-8"))
            mutated["safety"]["dashboard_executes_commands"] = True
            path = Path(td) / "safe-mode.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--safe-mode", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("dashboard_executes_commands", proc.stderr)

    def test_rejects_missing_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SAFE_MODE.read_text(encoding="utf-8"))
            mutated["evidence"] = ["work/mission-state/not-here.json"]
            path = Path(td) / "safe-mode.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--safe-mode", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("evidence path missing", proc.stderr)

    def test_rejects_control_token(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SAFE_MODE.read_text(encoding="utf-8"))
            mutated["operator_sequence"][0]["instruction"] = "please reboot now"
            path = Path(td) / "safe-mode.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--safe-mode", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("forbidden executable/control token", proc.stderr)

    def test_rejects_tx11_gate_without_boot_evidence_json(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SAFE_MODE.read_text(encoding="utf-8"))
            for step in mutated["operator_sequence"]:
                if step["id"] == "tx11-2g-client-gate-plan":
                    step.pop("requires_tx11_boot_evidence_json", None)
                    step.pop("tx11_boot_evidence_json", None)
                    step["display_command"] = "powershell -NoProfile -ExecutionPolicy Bypass -File .\\tools\\run_w2_2g_tx11_gate.ps1"
            path = Path(td) / "safe-mode.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--safe-mode", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Tx11BootEvidenceJson", proc.stderr)


if __name__ == "__main__":
    unittest.main()
