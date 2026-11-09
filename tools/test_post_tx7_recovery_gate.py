#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_post_tx7_recovery.ps1"


class PostTx7RecoveryGateTests(unittest.TestCase):
    def test_plan_only_is_default_and_read_only(self) -> None:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OMPOSTTX7_RECOVERY_PLAN_PASS=1", result.stdout)
        self.assertIn('"mode":  "plan-only"', result.stdout)
        self.assertIn("verify_post_tx7_recovery_result.py", result.stdout)
        self.assertIn('"uart_opened":  false', result.stdout)
        self.assertIn('"flash":  false', result.stdout)
        self.assertIn("OPENMITRASTAR_POST_TX7_RECOVERY_READONLY", result.stdout)

    def test_execute_requires_ack_and_no_uart_flash_words(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Execution requires -Ack", source)
        self.assertIn("AllowedPrefix", source)
        self.assertIn("ramssh_exec.py", source)
        self.assertIn("verify_post_tx7_recovery_result.py", source)
        self.assertIn("OMPOSTTX7_RECOVERY_BEGIN", source)
        self.assertIn("tail -n 120", source)
        self.assertIn('@("up", "unknown")', source)
        self.assertIn("Misaligned Access", source)
        self.assertIn("5\\.10\\.260-openmitrastar-radiohw", source)
        self.assertIn("$PingExit -eq 0", source)
        self.assertIn("result_verifier_ok", source)
        self.assertIn("recovery-result-verifier.stdout.json", source)
        self.assertIn('if ($null -eq $Stdout) { $Stdout = "" }', source)
        self.assertIn('if ($null -eq $Stderr) { $Stderr = "" }', source)
        for forbidden in (
            "flash_erase",
            "mtd_debug",
            "fw_setenv",
            "reboot -f",
            "COM3",
            "mode COM",
            "bootm",
            "ATGO",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
