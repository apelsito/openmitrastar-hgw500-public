#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/resume_post_tx7_5g_hang.ps1"


class ResumePostTx7HangTests(unittest.TestCase):
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

    def test_plan_only_default(self) -> None:
        result = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OMPOSTTX7_RESUME_PLAN_PASS=1", result.stdout)
        self.assertIn('"mode":  "plan-only"', result.stdout)
        self.assertIn("verify_post_tx7_recovery.ps1", result.stdout)
        self.assertIn("verify_router_lyoko_reentry.ps1", result.stdout)
        self.assertIn("verify_resume_post_tx7_result.py", result.stdout)
        self.assertIn("output_dir", result.stdout)
        self.assertIn('"lyoko_reentry_required_for_resume":  false', result.stdout)
        self.assertIn("collect_w2_tx11_boot_evidence.ps1", result.stdout)
        self.assertIn("run_w2_2g_tx11_gate.ps1", result.stdout)
        self.assertIn("ACK-gated TX11 exact RAM boot and client execution gate", result.stdout)
        self.assertIn('"uart_opened":  false', result.stdout)
        self.assertIn('"flash":  false', result.stdout)

    def test_execute_requires_resume_ack(self) -> None:
        result = self.run_script("-ExecuteRecovery")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY", result.stderr)

    def test_source_is_readonly_orchestration_only(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("OPENMITRASTAR_POST_TX7_RECOVERY_READONLY", source)
        self.assertIn("OPENMITRASTAR_LYOKO_REENTRY_READONLY", source)
        self.assertIn("verify_resume_post_tx7_result.py", source)
        self.assertIn("resume-result.json", source)
        self.assertIn("result_verifier_ok", source)
        self.assertIn("recovery-result.json", source)
        self.assertIn("recovery_result_json=", source)
        self.assertIn("lyoko-reentry-result.json", source)
        self.assertIn("collect_w2_tx11_boot_evidence.ps1", source)
        self.assertIn("run_w2_2g_tx11_gate.ps1", source)
        self.assertIn("OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1", source)
        self.assertIn("OM2G_TX11_GATE_PLAN_PASS=1", source)
        self.assertIn("VerifyLyokoReentry", source)
        for forbidden in (
            "flash_erase",
            "mtd_debug",
            "fw_setenv",
            "saveenv",
            "bootm",
            "ATGO",
            "mode COM",
            "om-radio5-start",
            "run_qtn_w3_tx7_client_traffic",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
