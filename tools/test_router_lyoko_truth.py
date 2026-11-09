#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "tools/compile_router_lyoko_truth.py"


def run_compiler(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COMPILER), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoTruthTests(unittest.TestCase):
    def test_truth_compiler_outputs_expected_schema_and_gates(self):
        proc = run_compiler()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["schema"], "router-lyoko.truth/v1")
        self.assertEqual(doc["classification"], "EVIDENCE-LEDGER-READONLY-NO-FLASH")
        gate_ids = {gate["id"]: gate for gate in doc["gates"]}
        for expected in (
            "phase1.kernel-linux510",
            "phase1.current-post-tx7-recovery",
            "phase1.bridge-ethernet-ssh",
            "phase2.realtek-2g-complete",
            "phase2.quantenna-5g",
            "phase3.lyoko-readonly-dashboard",
            "phase3.safe-control-policy",
            "phase3.lyoko-memory-agents-control",
        ):
            self.assertIn(expected, gate_ids)

    def test_truth_compiler_does_not_overclaim_known_pending_gates(self):
        proc = run_compiler()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        gate_ids = {gate["id"]: gate for gate in doc["gates"]}
        recovery_status = gate_ids["phase1.current-post-tx7-recovery"]["status"]
        self.assertIn(recovery_status, {"BLOCKED", "PROVEN"})
        recovery_evidence_status = {
            ev["path"]: ev["status"]
            for ev in gate_ids["phase1.current-post-tx7-recovery"]["evidence"]
        }
        self.assertEqual(recovery_evidence_status["tools/verify_post_tx7_recovery.ps1"], "READY")
        self.assertEqual(recovery_evidence_status["tools/verify_post_tx7_recovery_result.py"], "READY")
        self.assertEqual(recovery_evidence_status["tools/test_post_tx7_recovery_result_verifier.py"], "READY")
        self.assertEqual(recovery_evidence_status["tools/resume_post_tx7_5g_hang.ps1"], "READY")
        self.assertEqual(recovery_evidence_status["tools/verify_resume_post_tx7_result.py"], "READY")
        self.assertEqual(recovery_evidence_status["tools/test_resume_post_tx7_result_verifier.py"], "READY")
        recovery_evidence = "\n".join(
            f"{ev['status']} {ev['path']} {ev['claim']}"
            for ev in gate_ids["phase1.current-post-tx7-recovery"]["evidence"]
        )
        self.assertIn("autovalida recovery-result.json", recovery_evidence)
        self.assertIn("ping", recovery_evidence)
        self.assertIn("patrones fatales", recovery_evidence)
        self.assertIn("path escape", recovery_evidence)
        self.assertIn("secretos concretos", recovery_evidence)
        self.assertIn("sin eco del valor", recovery_evidence)
        self.assertIn("guard anti-secretos del recovery", recovery_evidence)
        self.assertIn("stdout/stderr top-level", recovery_evidence)
        self.assertIn("resultado top-level autoconsistente", recovery_evidence)
        self.assertIn("recovery_result_json", recovery_evidence)
        self.assertIn("RAM boot exacto TX11", recovery_evidence)
        self.assertIn("marcadores de planes TX11", recovery_evidence)
        if recovery_status == "BLOCKED":
            self.assertEqual(gate_ids["phase1.bridge-ethernet-ssh"]["status"], "BLOCKED")
            self.assertEqual(gate_ids["phase2.realtek-2g-complete"]["status"], "BLOCKED")
            self.assertEqual(gate_ids["phase2.quantenna-5g"]["status"], "BLOCKED")
            self.assertEqual(doc["summary"]["next_gate"], "phase1.current-post-tx7-recovery")
        else:
            self.assertEqual(gate_ids["phase1.bridge-ethernet-ssh"]["status"], "PARTIAL")
            self.assertEqual(gate_ids["phase2.realtek-2g-complete"]["status"], "PARTIAL")
            self.assertEqual(gate_ids["phase2.quantenna-5g"]["status"], "PARTIAL")
            self.assertIn(doc["summary"]["next_gate"], {"phase1.bridge-ethernet-ssh", "phase2.realtek-2g-complete"})
        realtek_evidence = "\n".join(ev["claim"] for ev in gate_ids["phase2.realtek-2g-complete"]["evidence"])
        self.assertIn("beacon/RF", realtek_evidence)
        self.assertIn("TX11-green-boot-controls", gate_ids["phase2.realtek-2g-complete"]["next_discriminant"])
        if recovery_status == "BLOCKED":
            self.assertIn("recovery-result.json verificado", gate_ids["phase2.realtek-2g-complete"]["next_discriminant"])
        else:
            self.assertIn("cliente iPhone AUTHORIZED", gate_ids["phase2.realtek-2g-complete"]["next_discriminant"])
        self.assertIn("Misaligned Access", "\n".join(ev["claim"] for ev in gate_ids["phase2.quantenna-5g"]["evidence"]))
        self.assertEqual(gate_ids["phase3.lyoko-readonly-dashboard"]["status"], "READY")
        self.assertEqual(gate_ids["phase3.safe-control-policy"]["status"], "READY")
        self.assertEqual(gate_ids["phase3.lyoko-memory-agents-control"]["status"], "PENDING")
        readonly_evidence = "\n".join(
            f"{ev['status']} {ev['path']} {ev['claim']}"
            for ev in gate_ids["phase3.lyoko-readonly-dashboard"]["evidence"]
        )
        self.assertIn("tools/verify_router_lyoko_reentry.ps1", readonly_evidence)
        self.assertIn("tools/test_router_lyoko_reentry_execution_fixture.py", readonly_evidence)
        self.assertIn("tools/verify_router_lyoko_reentry_result.py", readonly_evidence)
        self.assertIn("tools/test_router_lyoko_reentry_result_verifier.py", readonly_evidence)
        self.assertIn("tools/verify_router_lyoko_live.py", readonly_evidence)
        self.assertIn("tools/test_router_lyoko_live_verifier.py", readonly_evidence)
        self.assertIn("tools/verify_router_lyoko_objective_coverage.py", readonly_evidence)
        self.assertIn("tools/test_router_lyoko_objective_coverage.py", readonly_evidence)
        self.assertIn("cobertura del objetivo", readonly_evidence)
        self.assertIn("tools/integrate_router_lyoko_overlay.py", readonly_evidence)
        self.assertIn("tools/test_router_lyoko_integrator.py", readonly_evidence)
        self.assertIn("tools/sync_router_lyoko_static_data.py", readonly_evidence)
        self.assertIn("tools/test_router_lyoko_static_data.py", readonly_evidence)
        self.assertIn("tools/package_router_lyoko_overlay.py", readonly_evidence)
        self.assertIn("tools/test_package_router_lyoko_overlay.py", readonly_evidence)
        self.assertIn("tools/verify_router_lyoko_static_index.py", readonly_evidence)
        self.assertIn("tools/verify_router_lyoko_served_files.py", readonly_evidence)
        self.assertIn("tools/verify_router_lyoko_served_no_secrets.py", readonly_evidence)
        self.assertIn("tools/test_router_lyoko_served_no_secrets_verifier.py", readonly_evidence)
        self.assertIn("source-to-served", readonly_evidence)
        self.assertIn("served_file_drift", readonly_evidence)
        self.assertIn("manifest_drift", readonly_evidence)
        self.assertIn("sha256sums_drift", readonly_evidence)
        self.assertIn("static Lyoko truth stale", readonly_evidence)
        self.assertIn("rootfs RAM-test", readonly_evidence)
        self.assertIn("antes de copiar", readonly_evidence)
        self.assertIn("GET /api/lyoko", readonly_evidence)
        self.assertIn("/api/lyoko-control", readonly_evidence)
        self.assertIn("/lyoko-data/index.json", readonly_evidence)
        self.assertIn("/lyoko.html", readonly_evidence)
        self.assertIn("/lyoko.css", readonly_evidence)
        self.assertIn("/lyoko.js", readonly_evidence)
        self.assertIn("manifest", readonly_evidence)
        self.assertIn("control fail-closed", readonly_evidence)
        self.assertIn("static index sin drift", readonly_evidence)
        self.assertIn("served files sin drift", readonly_evidence)
        self.assertIn("served no-secrets", readonly_evidence)
        self.assertIn("verificación del propio lyoko-reentry-result.json", readonly_evidence)
        self.assertIn("HTTP fixture", readonly_evidence)
        self.assertIn("fail-closed", readonly_evidence)
        self.assertIn("PASS forjado", readonly_evidence)
        self.assertIn("secreto en API", readonly_evidence)
        self.assertIn("stdout JSON", readonly_evidence)
        self.assertIn("output_dir", readonly_evidence)
        self.assertIn("mutaciones falsas", readonly_evidence)
        self.assertIn("runtime_status", readonly_evidence)
        self.assertIn("system/ports/radios/clients/bridge/recovery", readonly_evidence)
        self.assertIn("Cobertura runtime", readonly_evidence)
        self.assertIn("sin clients", readonly_evidence)
        self.assertIn("recovery write-capable", readonly_evidence)
        self.assertIn("estado caído", readonly_evidence)
        self.assertIn("control write-capable", readonly_evidence)
        self.assertIn("índice inseguro", readonly_evidence)
        self.assertIn("/lyoko.js corrupto", readonly_evidence)
        self.assertIn("READY", readonly_evidence)
        self.assertIn("/api/lyoko-control", gate_ids["phase3.lyoko-readonly-dashboard"]["next_discriminant"])
        self.assertIn("/lyoko-data/index.json", gate_ids["phase3.lyoko-readonly-dashboard"]["next_discriminant"])
        self.assertIn("/lyoko.html", gate_ids["phase3.lyoko-readonly-dashboard"]["next_discriminant"])
        self.assertIn("/lyoko.js", gate_ids["phase3.lyoko-readonly-dashboard"]["next_discriminant"])
        self.assertIn("/lyoko.css", gate_ids["phase3.lyoko-readonly-dashboard"]["next_discriminant"])
        phase3_evidence = "\n".join(
            f"{ev['status']} {ev['path']} {ev['claim']}"
            for ev in gate_ids["phase3.lyoko-memory-agents-control"]["evidence"]
        )
        for expected in (
            "rootfs/var/www/api/lyoko-control",
            "memory/aelita-memory.json",
            "evidence-bindings.json",
            "telemetry-contract.json",
            "tools/validate_router_lyoko_telemetry_contract.py",
            "tools/test_router_lyoko_telemetry_contract.py",
            "memory/aelita-dialogue.json",
            "tools/verify_router_lyoko_aelita_memory.py",
            "tools/test_router_lyoko_aelita_memory.py",
            "event-taxonomy.json",
            "READY",
        ):
            self.assertIn(expected, phase3_evidence)
        self.assertIn("live.runtime_status", phase3_evidence)
        self.assertIn("text-only", phase3_evidence)
        self.assertIn("cadena hash JSONL", phase3_evidence)
        self.assertIn("hardware_claim", phase3_evidence)
        self.assertIn("frescura fail-closed", phase3_evidence)
        self.assertIn("mission_data.*", phase3_evidence)
        self.assertIn("endpoints runtime incorrectos", phase3_evidence)
        self.assertIn("siguen sin probarse", phase3_evidence)
        self.assertNotEqual(gate_ids["phase1.bridge-ethernet-ssh"]["status"], "PROVEN")

    def test_truth_compiler_write_outputs_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            json_out = Path(td) / "truth.json"
            md_out = Path(td) / "truth.md"
            proc = run_compiler("--write", "--json-out", str(json_out), "--md-out", str(md_out))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(json_out.is_file())
            self.assertTrue(md_out.is_file())
            self.assertEqual(json.loads(json_out.read_text(encoding="utf-8"))["schema"], "router-lyoko.truth/v1")
            self.assertIn("Router-Lyoko mission truth", md_out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
