#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/run_q3_v3_mtd4_promotion.py"
BACKEND = ROOT / "tools/q3_v3_mtd4_bootbase_flash.ps1"
PENDING = ROOT / "work/mission-state/q3-v3-mtd4-promotion/association-evidence.REQUIRED.json"
CANDIDATE_SHA = "1f0c1bf5b29c77c3670be9891db9da6bb3d186f0fb931b8de711a5b5d89c6296"


class PromotionGateTests(unittest.TestCase):
    def run_tool(self, evidence: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), "--association-evidence", str(evidence), "--output", str(output)],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def test_current_state_is_no_go_only_for_association(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            proc = self.run_tool(PENDING, output)
            self.assertEqual(2, proc.returncode, proc.stderr)
            plan = json.loads(output.read_text())
            self.assertEqual("NO_GO", plan["status"])
            self.assertFalse(plan["write_permitted"])
            self.assertEqual("client association and bidirectional traffic", plan["only_blocker"])
            failed = [name for name, value in plan["gates"].items() if value not in ("PASS", "PASS_ASSOCIATED", "PASS_ASSOCIATION_PENDING")]
            self.assertEqual(["client_association_and_traffic"], failed)

    def test_pass_associated_allows_dry_run_only(self) -> None:
        evidence = {
            "schema": "openmitrastar.q3-client-association-evidence/v1",
            "status": "PASS_ASSOCIATED",
            "candidate_sha256": CANDIDATE_SHA,
            "client_association": {"status": "PASS"},
            "client_traffic": {"status": "PASS"},
            "flash_actions": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            association = directory / "association.json"
            output = directory / "plan.json"
            association.write_text(json.dumps(evidence), encoding="utf-8")
            proc = self.run_tool(association, output)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("OMQ3_V3_MTD4_PROMOTION_GO_DRY_RUN", proc.stdout)
            plan = json.loads(output.read_text())
            self.assertEqual("GO", plan["status"])
            self.assertTrue(plan["write_permitted"])
            self.assertFalse(plan["execute_requested"])
            self.assertFalse(plan["flash_actions"])
            self.assertFalse(plan["hardware_actions"])

    def test_backend_rechecks_association_before_write(self) -> None:
        text = BACKEND.read_text(encoding="utf-8")
        association = text.index("PASS_ASSOCIATED evidence contract failed")
        erase = text.index("spi_flash erase")
        self.assertLess(association, erase)
        self.assertIn("OPENMITRASTAR_Q3_V3_MTD4_FLASH_1F0C1BF5_PASS_ASSOCIATED", text)
        self.assertIn("OMPRODUCT_ENTROPY_LOCAL_OK source=jitterentropy_rng", text)
        self.assertIn("target=mtd4", text)
        self.assertNotIn("spi_flash erase 0x00000000", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
