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
SCRIPT = ROOT / "tools/verify_resume_post_tx7_result.py"
RECOVERY_OUTPUTS = ROOT / "outputs/recovery"


def load_report(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(proc.stdout)


class ResumePostTx7ResultVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        RECOVERY_OUTPUTS.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(tempfile.mkdtemp(prefix="resume-post-tx7-result-test-", dir=RECOVERY_OUTPUTS))
        self.recovery_dir = self.output_dir / "post-tx7-recovery"
        self.lyoko_dir = self.output_dir / "router-lyoko-reentry"
        self.recovery_dir.mkdir()
        self.lyoko_dir.mkdir()
        self.result_path = self.output_dir / "resume-result.json"
        self.write_result(pass_value=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def write_child_results(self, *, recovery_pass: bool = True, lyoko_pass: bool = True) -> tuple[Path, Path]:
        recovery_result = self.recovery_dir / "recovery-result.json"
        recovery_result.write_text(
            json.dumps(
                {
                    "schema": "openmitrastar.post-tx7-recovery-result/v1",
                    "pass": recovery_pass,
                    "result_verifier_ok": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        lyoko_result = self.lyoko_dir / "lyoko-reentry-result.json"
        lyoko_result.write_text(
            json.dumps(
                {
                    "schema": "router-lyoko.reentry-live-api-result/v1",
                    "pass": lyoko_pass,
                    "result_verifier_ok": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return recovery_result, lyoko_result

    def write_result(
        self,
        *,
        pass_value: bool,
        recovery_exit: int = 0,
        recovery_pass: bool = True,
        lyoko_required: bool = False,
        lyoko_exit: int | None = -1,
        lyoko_pass: bool = False,
        tx11_boot_plan_exit: int = 0,
        tx11_boot_plan_ready: bool = True,
        tx11_2g_plan_exit: int = 0,
        tx11_2g_plan_ready: bool = True,
        tx11_boot_plan_stdout: str = "OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1 variant=TX11\n",
        tx11_2g_plan_stdout: str = "OM2G_TX11_GATE_PLAN_PASS=1 variant=TX11\n",
        mutations: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        mutations = mutations or {}
        recovery_result, lyoko_result = self.write_child_results(
            recovery_pass=recovery_pass,
            lyoko_pass=lyoko_pass,
        )
        paths = {
            "recovery_stdout": self.output_dir / "recovery.stdout.txt",
            "recovery_stderr": self.output_dir / "recovery.stderr.txt",
            "lyoko_stdout": self.output_dir / "lyoko-reentry.stdout.txt",
            "lyoko_stderr": self.output_dir / "lyoko-reentry.stderr.txt",
            "tx11_boot_plan_stdout": self.output_dir / "tx11-boot-evidence-plan.stdout.txt",
            "tx11_boot_plan_stderr": self.output_dir / "tx11-boot-evidence-plan.stderr.txt",
            "tx11_2g_plan_stdout": self.output_dir / "tx11-2g-plan.stdout.txt",
            "tx11_2g_plan_stderr": self.output_dir / "tx11-2g-plan.stderr.txt",
        }
        paths["recovery_stdout"].write_text("OMPOSTTX7_RECOVERY_PASS=1\n" if recovery_pass else "OMPOSTTX7_RECOVERY_PASS=0\n", encoding="utf-8")
        paths["recovery_stderr"].write_text("", encoding="utf-8")
        paths["lyoko_stdout"].write_text("OMLYOKO_REENTRY_PASS=1\n" if lyoko_pass else "OMLYOKO_REENTRY_PASS=0\n", encoding="utf-8")
        paths["lyoko_stderr"].write_text("", encoding="utf-8")
        paths["tx11_boot_plan_stdout"].write_text(tx11_boot_plan_stdout, encoding="utf-8")
        paths["tx11_boot_plan_stderr"].write_text("", encoding="utf-8")
        paths["tx11_2g_plan_stdout"].write_text(tx11_2g_plan_stdout, encoding="utf-8")
        paths["tx11_2g_plan_stderr"].write_text("", encoding="utf-8")
        result = {
            "schema": "openmitrastar.resume-post-tx7-5g-hang-result/v1",
            "status": "RESUME_POST_TX7_READY_FOR_2G_CLIENT_GATE" if pass_value else "RESUME_POST_TX7_NOT_READY",
            "pass": pass_value,
            "host": "192.168.1.90",
            "recovery_exit": recovery_exit,
            "recovery_pass": recovery_pass,
            "lyoko_reentry_required": lyoko_required,
            "lyoko_reentry_exit": lyoko_exit,
            "lyoko_reentry_pass": lyoko_pass,
            "tx11_boot_plan_exit": tx11_boot_plan_exit,
            "tx11_boot_plan_ready": tx11_boot_plan_ready,
            "tx11_2g_plan_exit": tx11_2g_plan_exit,
            "tx11_2g_plan_ready": tx11_2g_plan_ready,
            "evidence": {
                "output_dir": str(self.output_dir),
                "recovery_stdout": str(paths["recovery_stdout"]),
                "recovery_stderr": str(paths["recovery_stderr"]),
                "recovery_result_json": str(recovery_result),
                "lyoko_stdout": str(paths["lyoko_stdout"]) if lyoko_required else "",
                "lyoko_stderr": str(paths["lyoko_stderr"]) if lyoko_required else "",
                "lyoko_result_json": str(lyoko_result) if lyoko_required else "",
                "tx11_boot_plan_stdout": str(paths["tx11_boot_plan_stdout"]),
                "tx11_boot_plan_stderr": str(paths["tx11_boot_plan_stderr"]),
                "tx11_2g_plan_stdout": str(paths["tx11_2g_plan_stdout"]),
                "tx11_2g_plan_stderr": str(paths["tx11_2g_plan_stderr"]),
                "result_json": str(self.result_path),
            },
            "mutations": {
                "uart_opened": False,
                "module_reload": False,
                "network_reconfigure": False,
                "bootenv": False,
                "mtd": False,
                "flash": False,
                **mutations,
            },
        }
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

    def test_accepts_coherent_resume_without_lyoko_reentry(self) -> None:
        proc = self.run_verifier()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        report = load_report(proc)
        self.assertTrue(report["ok"])
        checks = {check["id"]: check["ok"] for check in report["checks"]}
        self.assertTrue(checks["pass.matches_children"])
        self.assertTrue(checks["status.matches_pass"])

    def test_accepts_coherent_resume_with_required_lyoko_reentry(self) -> None:
        self.write_result(
            pass_value=True,
            lyoko_required=True,
            lyoko_exit=0,
            lyoko_pass=True,
        )
        proc = self.run_verifier()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertTrue(load_report(proc)["ok"])

    def test_rejects_forged_pass_when_recovery_child_failed(self) -> None:
        self.write_result(pass_value=True, recovery_exit=2, recovery_pass=False)
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("pass.matches_children", failed)

    def test_rejects_missing_tx11_boot_plan_marker(self) -> None:
        self.write_result(pass_value=True, tx11_boot_plan_ready=True, tx11_boot_plan_stdout="plan only but no marker\n")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("tx11_boot_plan_ready.matches_stdout", failed)
        self.assertIn("pass.matches_children", failed)

    def test_rejects_missing_tx11_2g_plan_marker(self) -> None:
        self.write_result(pass_value=True, tx11_2g_plan_ready=True, tx11_2g_plan_stdout="plan only but no marker\n")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("tx11_2g_plan_ready.matches_stdout", failed)
        self.assertIn("pass.matches_children", failed)

    def test_rejects_mutation_flag_enabled(self) -> None:
        self.write_result(pass_value=True, mutations={"flash": True})
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("mutations.flash.false", failed)

    def test_rejects_evidence_path_escape(self) -> None:
        outside = self.output_dir.parent / "outside-resume-tx11-plan.stdout.txt"
        try:
            outside.write_text("OM2G_TX11_GATE_PLAN_PASS=1\n", encoding="utf-8")
            payload = json.loads(self.result_path.read_text(encoding="utf-8"))
            payload["evidence"]["tx11_2g_plan_stdout"] = str(outside)
            self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            proc = self.run_verifier()
            self.assertEqual(1, proc.returncode)
            failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
            self.assertIn("evidence.tx11_2g_plan_stdout.under_output_dir", failed)
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_secret_bearing_top_level_stdout_without_echoing_secret(self) -> None:
        secret_value = "resume-secret-router-key"
        self.write_result(pass_value=True, tx11_2g_plan_stdout=f"OM2G_TX11_GATE_PLAN_PASS=1\nwpa_psk={secret_value}\n")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        self.assertNotIn(secret_value, proc.stdout)
        self.assertNotIn(secret_value, proc.stderr)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("tx11_2g_plan_stdout.no_secrets", failed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
