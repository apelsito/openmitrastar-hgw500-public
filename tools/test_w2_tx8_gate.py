#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools/audit_w2_tx8_candidate.py"
VERIFY = ROOT / "tools/verify_w2_tx7_gate_for_tx8.py"
WRAPPER = ROOT / "tools/run_w2_2g_tx8_gate.ps1"


class Tx8GateTests(unittest.TestCase):
    def test_candidate_audit_passes_exact_current_artifact(self) -> None:
        proc = subprocess.run([sys.executable, str(AUDIT)], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["image"]["sha256"], "387eedd890be8d22c55c6fbd3d14cb4f2e11c83ac5a72059c3edde1176d5ac19")
        self.assertTrue(report["slot"]["fits"])
        self.assertFalse(report["flash_supported"])

    def test_wrapper_defaults_to_locked_plan_only(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WRAPPER)],
            cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM2G_TX8_GATE_PLAN_PASS=1", proc.stdout)
        self.assertIn("OM2G_TX8_EXECUTION_LOCKED_UNTIL_TX7_CLIENT_RX_UNALIGNED_PROOF=1", proc.stdout)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_current_no_client_tx7_result_cannot_unlock_tx8(self) -> None:
        gate = ROOT / "outputs/kernel-port/realtek-loop/w2-tx7-live-gate-20260822-114348-RAM-ONLY-NO-FLASH/gate-result.json"
        proc = subprocess.run(
            [sys.executable, str(VERIFY), str(gate)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "TX8_LOCKED")
        self.assertIn("gate.not_no_client", report["failed_checks"])
        self.assertIn("summary.associated", report["failed_checks"])

    def test_valid_client_rx_unaligned_fixture_unlocks_proof_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "monitor.log.json"
            raw = root / "monitor.log"
            gate = root / "gate-result.json"
            manifest = root / "run-manifest.json"
            fault = root / "uart.log"
            summary.write_text(json.dumps({
                "association_observed": True,
                "authorization_observed": True,
                "fatal_markers_during_run": 1,
                "flash": False,
                "mutations": False,
                "raw_log": str(raw),
            }), encoding="utf-8")
            raw.write_text("client gate terminated after fault\n", encoding="utf-8")
            gate.write_text(json.dumps({
                "schema": "openmitrastar.w2-2g-live-traffic-evaluation/v1",
                "status": "FAIL",
                "pass": False,
                "input": str(summary),
            }), encoding="utf-8")
            manifest.write_text(json.dumps({
                "schema": "openmitrastar.w2-candidate-live-gate-run/v1",
                "classification": "RAM-ONLY-TX7-NO-FLASH-READ-ONLY-SSH",
                "image": {"sha256": "d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3", "bytes": 4330928},
                "uart_opened": False, "module_reload": False, "reboot": False, "flash": False,
            }), encoding="utf-8")
            fault.write_text("Misaligned r/w from 0x86f900a9\nECR: 0 EFA: 0x86f900a9 ERET: 0\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(VERIFY), str(gate), "--fault-log", str(fault)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(json.loads(proc.stdout)["ok"])

    def test_wrapper_source_has_no_boot_or_flash_path(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("run_w2_2g_candidate_gate.ps1", text)
        self.assertIn("verify_w2_tx7_gate_for_tx8.py", text)
        self.assertIn("ExecuteGate", text)
        self.assertNotIn("COM3", text)
        self.assertNotIn("bootm", text.lower())
        self.assertNotIn("flash_erase", text.lower())
        self.assertNotIn("fw_setenv", text.lower())


if __name__ == "__main__":
    unittest.main()
