#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/validate_router_lyoko_control_policy.py"
POLICY = ROOT / "work/mission-state/router-lyoko-v0/control/control-policy.json"


def run_validator(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoControlPolicyTests(unittest.TestCase):
    def test_current_policy_is_valid(self):
        proc = run_validator(POLICY)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["mode"], "observe_only")

    def test_rejects_allowed_action_that_writes_device(self):
        with tempfile.TemporaryDirectory() as td:
            policy = json.loads(POLICY.read_text(encoding="utf-8"))
            policy["current_allowed_actions"].append(
                {
                    "id": "bad.flash",
                    "label": "bad",
                    "type": "lab_command",
                    "target": "flashcp image.bin /dev/mtd4",
                    "writes_device": False,
                }
            )
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            proc = run_validator(path)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("forbidden token", proc.stderr)

    def test_rejects_unblocked_module_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            policy = json.loads(POLICY.read_text(encoding="utf-8"))
            policy["blocked_actions"] = [
                action
                for action in policy["blocked_actions"]
                if action["id"] != "control.module_reload"
            ]
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            proc = run_validator(path)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("missing blocked actions", proc.stderr)

    def test_rejects_dangerous_action_without_post_tx7_recovery_gate(self):
        with tempfile.TemporaryDirectory() as td:
            policy = json.loads(POLICY.read_text(encoding="utf-8"))
            for action in policy["blocked_actions"]:
                if action["id"] == "control.radio_mutation":
                    action["blocked_until"] = [
                        gate
                        for gate in action["blocked_until"]
                        if gate != "phase1.current-post-tx7-recovery=PROVEN"
                    ]
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            proc = run_validator(path)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("post-TX7 recovery gate", proc.stderr)

    def test_rejects_quantenna_start_without_symbolization_gate(self):
        with tempfile.TemporaryDirectory() as td:
            policy = json.loads(POLICY.read_text(encoding="utf-8"))
            for action in policy["blocked_actions"]:
                if action["id"] == "control.quantenna_5g_start":
                    action["blocked_until"] = [
                        gate
                        for gate in action["blocked_until"]
                        if gate != "qdrv.tx7_misaligned_access_symbolized=PROVEN"
                    ]
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            proc = run_validator(path)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("5 GHz start gate missing", proc.stderr)

    def test_rejects_safe_control_promotion_without_post_tx7_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            policy = json.loads(POLICY.read_text(encoding="utf-8"))
            policy["promotion_gates"]["observe_only_to_safe_control"] = [
                gate
                for gate in policy["promotion_gates"]["observe_only_to_safe_control"]
                if gate != "post-TX7 recovery PASS on current boot"
            ]
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            proc = run_validator(path)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("post-TX7 recovery PASS", proc.stderr)


if __name__ == "__main__":
    unittest.main()
