#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_router_lyoko_reentry_result.py"
RECOVERY_OUTPUTS = ROOT / "outputs/recovery"


LANES = {
    "state": {
        "exit_field": "state_verifier_exit",
        "ok_field": "state_verifier_ok",
        "stdout_key": "state_verifier_stdout",
        "stderr_key": "state_verifier_stderr",
        "stdout_name": "lyoko-live-verifier.stdout.json",
        "stderr_name": "lyoko-live-verifier.stderr.txt",
        "classification": "READONLY-LIVE-VERIFY-NO-CONTROL",
    },
    "control": {
        "exit_field": "control_verifier_exit",
        "ok_field": "control_verifier_ok",
        "stdout_key": "control_verifier_stdout",
        "stderr_key": "control_verifier_stderr",
        "stdout_name": "lyoko-control-verifier.stdout.json",
        "stderr_name": "lyoko-control-verifier.stderr.txt",
        "classification": "READONLY-CONTROL-CONTRACT-VERIFY-NO-CONTROL",
    },
    "static_index": {
        "exit_field": "static_index_verifier_exit",
        "ok_field": "static_index_verifier_ok",
        "stdout_key": "static_index_verifier_stdout",
        "stderr_key": "static_index_verifier_stderr",
        "stdout_name": "lyoko-static-index-verifier.stdout.json",
        "stderr_name": "lyoko-static-index-verifier.stderr.txt",
        "classification": "READONLY-STATIC-INDEX-VERIFY-NO-CONTROL",
    },
    "served_files": {
        "exit_field": "served_files_verifier_exit",
        "ok_field": "served_files_verifier_ok",
        "stdout_key": "served_files_verifier_stdout",
        "stderr_key": "served_files_verifier_stderr",
        "stdout_name": "lyoko-served-files-verifier.stdout.json",
        "stderr_name": "lyoko-served-files-verifier.stderr.txt",
        "classification": "READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL",
    },
    "served_no_secrets": {
        "exit_field": "served_no_secrets_verifier_exit",
        "ok_field": "served_no_secrets_verifier_ok",
        "stdout_key": "served_no_secrets_verifier_stdout",
        "stderr_key": "served_no_secrets_verifier_stderr",
        "stdout_name": "lyoko-served-no-secrets-verifier.stdout.json",
        "stderr_name": "lyoko-served-no-secrets-verifier.stderr.txt",
        "classification": "READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL",
    },
}
REQUIRED_SERVED_FILES_CHECKS = [
    "served./lyoko-data/safe-mode.json.tx11_requires_exact_boot",
    "served./lyoko-data/safe-mode.json.tx11_boot_collector_command",
    "served./lyoko-data/safe-mode.json.tx11_requires_boot_evidence_json",
    "served./lyoko-data/safe-mode.json.tx11_command_boot_evidence_json",
    "served./lyoko.js.fetches_safe_mode_contract",
    "served./lyoko.js.tx11_boot_evidence_guard_visible",
]


def load_stdout_json(stdout: str) -> dict[str, Any]:
    return json.loads(stdout)


class RouterLyokoReentryResultVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        RECOVERY_OUTPUTS.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(tempfile.mkdtemp(prefix="lyoko-reentry-result-test-", dir=RECOVERY_OUTPUTS))
        self.result_path = self.output_dir / "lyoko-reentry-result.json"
        self.result = self.write_result(pass_value=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def write_result(
        self,
        *,
        pass_value: bool,
        lane_ok: dict[str, bool] | None = None,
        exits: dict[str, int] | None = None,
        stdout_ok: dict[str, bool] | None = None,
        mutations: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        lane_ok = lane_ok or {}
        exits = exits or {}
        stdout_ok = stdout_ok or {}
        mutations = mutations or {}
        evidence: dict[str, str] = {"output_dir": str(self.output_dir)}
        result: dict[str, Any] = {
            "schema": "router-lyoko.reentry-live-api-result/v1",
            "status": "LYOKO_REENTRY_PROVEN_READONLY" if pass_value else "LYOKO_REENTRY_NOT_PROVEN",
            "pass": pass_value,
            "host": "127.0.0.1:12345",
            "mutations": {
                "uart_opened": False,
                "ssh_command": False,
                "reboot": False,
                "network_reconfigure": False,
                "bootenv": False,
                "mtd": False,
                "flash": False,
                **mutations,
            },
        }
        for lane, spec in LANES.items():
            ok = lane_ok.get(lane, pass_value)
            stdout_value = stdout_ok.get(lane, ok)
            stdout_checks = [
                {"id": check_id, "ok": True, "detail": "fixture semantic guard"}
                for check_id in REQUIRED_SERVED_FILES_CHECKS
            ] if lane == "served_files" else []
            result[spec["exit_field"]] = exits.get(lane, 0 if ok else 1)
            result[spec["ok_field"]] = ok
            stdout_path = self.output_dir / spec["stdout_name"]
            stderr_path = self.output_dir / spec["stderr_name"]
            stdout_path.write_text(
                json.dumps(
                    {
                        "ok": stdout_value,
                        "classification": spec["classification"],
                        "checks": stdout_checks,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")
            evidence[spec["stdout_key"]] = str(stdout_path)
            evidence[spec["stderr_key"]] = str(stderr_path)
        evidence["result_json"] = str(self.result_path)
        result["evidence"] = evidence
        self.result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def run_verifier(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.result_path), "--output-dir", str(self.output_dir)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_accepts_coherent_pass_result_with_all_evidence(self) -> None:
        proc = self.run_verifier()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        report = load_stdout_json(proc.stdout)
        self.assertTrue(report["ok"])
        check_ids = {check["id"]: check["ok"] for check in report["checks"]}
        self.assertTrue(check_ids["pass.matches_lanes"])
        self.assertTrue(check_ids["status.matches_pass"])
        self.assertTrue(check_ids["state.stdout.classification"])
        self.assertTrue(check_ids["served_files.stdout.classification"])
        self.assertTrue(check_ids["served_no_secrets.stdout.classification"])
        self.assertTrue(check_ids["served_files.stdout.safe_mode_tx11_requires_exact_boot"])
        self.assertTrue(check_ids["served_files.stdout.safe_mode_tx11_boot_collector_command"])
        self.assertTrue(check_ids["served_files.stdout.safe_mode_tx11_requires_boot_evidence_json"])
        self.assertTrue(check_ids["served_files.stdout.safe_mode_tx11_command_boot_evidence_json"])
        self.assertTrue(check_ids["served_files.stdout.lyoko_js_fetches_safe_mode_contract"])
        self.assertTrue(check_ids["served_files.stdout.lyoko_js_tx11_boot_evidence_guard_visible"])

    def test_rejects_forged_pass_true_when_lane_failed(self) -> None:
        self.write_result(
            pass_value=True,
            lane_ok={"served_no_secrets": False},
            exits={"served_no_secrets": 1},
            stdout_ok={"served_no_secrets": False},
        )
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        report = load_stdout_json(proc.stdout)
        self.assertFalse(report["ok"])
        failed = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("pass.matches_lanes", failed)

    def test_rejects_missing_evidence_file(self) -> None:
        missing = Path(self.result["evidence"]["control_verifier_stdout"])
        missing.unlink()
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        report = load_stdout_json(proc.stdout)
        failed = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("evidence.control_verifier_stdout.exists", failed)
        self.assertIn("control.stdout.json", failed)

    def test_rejects_mutation_flag_enabled(self) -> None:
        self.write_result(pass_value=True, mutations={"flash": True})
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        report = load_stdout_json(proc.stdout)
        failed = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("mutations.flash.false", failed)

    def test_rejects_stdout_ok_mismatch(self) -> None:
        self.write_result(pass_value=True, stdout_ok={"state": False})
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        report = load_stdout_json(proc.stdout)
        failed = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("state.stdout.ok.matches_result", failed)
        self.assertIn("pass.matches_lanes", failed)

    def test_rejects_evidence_path_outside_output_dir(self) -> None:
        outside = self.output_dir.parent / "outside-lyoko-live-verifier.stdout.json"
        try:
            outside.write_text(
                json.dumps({"ok": True, "classification": LANES["state"]["classification"]}),
                encoding="utf-8",
            )
            payload = json.loads(self.result_path.read_text(encoding="utf-8"))
            payload["evidence"]["state_verifier_stdout"] = str(outside)
            self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            proc = self.run_verifier()
            self.assertEqual(1, proc.returncode)
            report = load_stdout_json(proc.stdout)
            failed = {check["id"] for check in report["checks"] if not check["ok"]}
            self.assertIn("evidence.state_verifier_stdout.under_output_dir", failed)
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_served_files_stdout_without_tx11_semantic_guard(self) -> None:
        stdout_path = Path(self.result["evidence"]["served_files_verifier_stdout"])
        payload = json.loads(stdout_path.read_text(encoding="utf-8"))
        payload["checks"] = [
            check
            for check in payload["checks"]
            if check.get("id") != "served./lyoko.js.tx11_boot_evidence_guard_visible"
        ]
        stdout_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        report = load_stdout_json(proc.stdout)
        failed = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("served_files.stdout.lyoko_js_tx11_boot_evidence_guard_visible", failed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
