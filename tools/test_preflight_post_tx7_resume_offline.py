#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/preflight_post_tx7_resume_offline.py"
CANDIDATE_GATE = ROOT / "tools/run_w2_2g_candidate_gate.ps1"


class PostTx7OfflinePreflightTests(unittest.TestCase):
    def run_preflight(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def parse_report(self, stdout: str) -> dict:
        decoder = json.JSONDecoder()
        report, _ = decoder.raw_decode(stdout.lstrip())
        return report

    def test_preflight_passes_offline_without_hardware(self) -> None:
        proc = self.run_preflight()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OMPOSTTX7_OFFLINE_PREFLIGHT_PASS=1", proc.stdout)
        report = self.parse_report(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["classification"], "READONLY-OFFLINE-PREFLIGHT-NO-HARDWARE")
        hardware_state = report["artifacts"].get("hardware_state", {})
        expected_next_gate = (
            "tx13-lossless-mgmt-trace-exact-ram-boot-and-capture"
            if hardware_state.get("recovery_evidence_verified") is True
            else "physical-power-cycle-then-ack-gated-readonly-recovery"
        )
        self.assertEqual(report["next_gate"], expected_next_gate)
        self.assertFalse(report["mutations"]["uart_opened"])
        self.assertFalse(report["mutations"]["ssh_command"])
        self.assertFalse(report["mutations"]["flash"])
        check_ids = {check["id"] for check in report["checks"]}
        self.assertIn("hardware_state.post_tx7_boot_state", check_ids)
        self.assertIn("recovery.plan.ack_required", check_ids)
        self.assertIn("resume.plan.ack_required", check_ids)
        self.assertIn("lyoko_reentry.requires_recovery_guards", check_ids)
        self.assertIn("tx7_2g.plan.marker", check_ids)
        self.assertIn("tx11_boot.plan.marker", check_ids)
        self.assertIn("tx11_boot.plan.requires_exact_ram_boot", check_ids)
        self.assertIn("tx11_boot.plan.locked_by_default", check_ids)
        self.assertIn("tx11_2g.plan.marker", check_ids)
        self.assertIn("tx11_2g.plan.requires_exact_boot_evidence", check_ids)
        self.assertIn("tx11_2g.plan.waits_for_authorized_client", check_ids)
        self.assertIn("tx11_2g.plan.locked_by_default", check_ids)
        self.assertIn("tx13_boot.plan.marker", check_ids)
        self.assertIn("tx13_boot.plan.ack_required", check_ids)
        self.assertIn("tx13_boot.plan.locked_by_default", check_ids)
        self.assertIn("tx13_trace.plan.marker", check_ids)
        self.assertIn("tx13_trace.plan.ack_required", check_ids)
        self.assertIn("tx13_trace.plan.locked_by_default", check_ids)
        self.assertIn("tx9_2g.plan.marker", check_ids)
        self.assertIn("tx9_2g.plan.requires_exact_boot_evidence", check_ids)
        self.assertIn("tx9_2g.plan.locked_by_default", check_ids)
        self.assertIn("recovery_result_verifier.no_secrets_guard", check_ids)
        self.assertIn("recovery_result_verifier.strict_eth0_link_guard", check_ids)
        self.assertIn("recovery_result_verifier_test.no_secret_echo_case", check_ids)
        self.assertIn("recovery_result_verifier_test.strict_eth0_link_cases", check_ids)
        self.assertIn("resume_result_verifier.no_secrets_guard", check_ids)
        self.assertIn("resume_result_verifier_test.no_secret_echo_case", check_ids)
        self.assertIn("aelita_memory_guard.returncode", check_ids)
        self.assertIn("aelita_memory_guard.ok", check_ids)
        self.assertIn("evidence_bindings_guard.returncode", check_ids)
        self.assertIn("evidence_bindings_guard.ok", check_ids)
        self.assertIn("objective_coverage_guard.returncode", check_ids)
        self.assertIn("objective_coverage_guard.ok", check_ids)
        self.assertIn("objective_coverage_guard.next_gate", check_ids)
        self.assertIn("current_offline_suite.list.returncode", check_ids)
        self.assertIn("current_offline_suite.list.marker", check_ids)
        self.assertIn("current_offline_suite.list.no_missing", check_ids)
        self.assertIn("current_offline_suite.list.expected_count", check_ids)
        self.assertIn("current_offline_suite.list.includes_required_boundaries", check_ids)
        self.assertIn("current_offline_suite.list.excludes_stale_release_gates", check_ids)
        self.assertIn("served_files_verifier.returncode", check_ids)
        self.assertIn("served_files_verifier.ok", check_ids)
        self.assertIn("served_files_verifier.safe_mode_tx11_boot_evidence_json", check_ids)
        self.assertIn("served_files_verifier.lyoko_js_safe_mode_source", check_ids)
        self.assertEqual(report["artifacts"]["aelita_memory_guard"]["returncode"], 0)
        self.assertEqual(report["artifacts"]["evidence_bindings_guard"]["returncode"], 0)
        self.assertEqual(report["artifacts"]["objective_coverage_guard"]["returncode"], 0)
        self.assertEqual(report["artifacts"]["current_offline_suite_list"]["returncode"], 0)
        self.assertEqual(report["artifacts"]["served_files_verifier"]["returncode"], 0)

    def test_preflight_rejects_wrong_expected_package_hash(self) -> None:
        proc = self.run_preflight("--expected-lyoko-sha256", "0" * 64)
        self.assertEqual(2, proc.returncode)
        self.assertIn("OMPOSTTX7_OFFLINE_PREFLIGHT_PASS=0", proc.stdout)
        report = self.parse_report(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("lyoko_package.sha256.expected", failing)

    def test_tx7_gate_has_get_file_hash_fallback(self) -> None:
        source = CANDIDATE_GATE.read_text(encoding="utf-8")
        self.assertIn("function Get-Sha256Hex", source)
        self.assertIn("Get-Command Get-FileHash -ErrorAction SilentlyContinue", source)
        self.assertIn("[System.Security.Cryptography.SHA256]::Create()", source)

    def test_preflight_source_contains_no_hardware_execution_flags(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("-ExecuteRecovery", source)
        self.assertNotIn("-Execute `", source)
        self.assertNotIn("ramssh_exec.py", source)
        self.assertNotIn("COM3", source)
        self.assertIn("READONLY-OFFLINE-PREFLIGHT-NO-HARDWARE", source)
        self.assertIn("recovery_result_verifier.no_secrets_guard", source)
        self.assertIn("recovery_result_verifier.strict_eth0_link_guard", source)
        self.assertIn("recovery_result_verifier_test.no_secret_echo_case", source)
        self.assertIn("recovery_result_verifier_test.strict_eth0_link_cases", source)
        self.assertIn("resume_result_verifier.no_secrets_guard", source)
        self.assertIn("resume_result_verifier_test.no_secret_echo_case", source)
        self.assertIn("aelita_memory_guard.ok", source)
        self.assertIn("verify_router_lyoko_aelita_memory.py", source)
        self.assertIn("evidence_bindings_guard.ok", source)
        self.assertIn("validate_router_lyoko_evidence_bindings.py", source)
        self.assertIn("objective_coverage_guard.ok", source)
        self.assertIn("verify_router_lyoko_objective_coverage.py", source)
        self.assertIn("run_router_lyoko_current_offline_suite.py", source)
        self.assertIn("current_offline_suite.list.excludes_stale_release_gates", source)
        self.assertIn("historical Q1/Q2/Q3/W5 product artifact tests", source)
        self.assertIn("verify_router_lyoko_served_files.py", source)
        self.assertIn("served_files_verifier.safe_mode_tx11_boot_evidence_json", source)
        self.assertIn("served_files_verifier.lyoko_js_safe_mode_source", source)
        self.assertIn("run_w2_2g_tx11_gate.ps1", source)
        self.assertIn("collect_w2_tx11_boot_evidence.ps1", source)
        self.assertIn("run_w2_tx13_ram_boot.ps1", source)
        self.assertIn("collect_w2_tx13_mgmt_trace.ps1", source)
        self.assertIn("wait_w2_2g_client.py", source)
        self.assertIn("tx11_boot.plan.requires_exact_ram_boot", source)
        self.assertIn("tx11_2g.plan.requires_exact_boot_evidence", source)
        self.assertIn("tx11_2g.plan.waits_for_authorized_client", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
