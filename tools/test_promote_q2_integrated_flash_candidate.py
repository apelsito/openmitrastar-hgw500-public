#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/promote_q2_integrated_flash_candidate.py"
CONTRACT = ROOT / "work/mission-state/F2_Q2_INTEGRATED_FLASH_CANDIDATE_INPUT_CONTRACT.json"
EXPECTED_SHA = "cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1"
EXPECTED_BYTES = 4_157_772


class PromoteQ2IntegratedCandidateTests(unittest.TestCase):
    def test_contract_uses_a_separate_q2_lane(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        inputs = contract["required_candidate_inputs"]
        self.assertEqual("work/mission-state/f2-q2-integrated-flash-candidate", inputs["directory"])
        self.assertNotIn("q1-full-flash-candidate", inputs["directory"])
        self.assertEqual(EXPECTED_SHA, contract["exact_image"]["sha256"])
        self.assertEqual(EXPECTED_BYTES, contract["exact_image"]["bytes"])

    def test_promotes_exact_q2_without_prior_attestations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--candidate-dir", str(destination)],
                cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("OMQ2_PROMOTION_PASS", proc.stdout)
            self.assertIn("prior_attestations_copied=0", proc.stdout)
            candidate = destination / "openmitrastar-linux510-q2-integrated-webformat.bin"
            manifest_path = destination / "manifest.json"
            self.assertEqual(EXPECTED_BYTES, candidate.stat().st_size)
            self.assertEqual(EXPECTED_SHA, hashlib.sha256(candidate.read_bytes()).hexdigest())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("Q2_PARITY_INTEGRATED", manifest["profile"])
            self.assertTrue(manifest["candidate_eligible"])
            self.assertFalse(manifest["flash_ready"])
            self.assertFalse(manifest["attestations_copied_from_prior_candidates"])
            self.assertEqual({"PENDING"}, set(manifest["runtime_gates"].values()))
            self.assertFalse((destination / "ram-equivalence.json").exists())
            self.assertFalse((destination / "current-flash-read.json").exists())

    def test_promoter_has_no_hardware_or_flash_execution_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "import serial", "import socket", "import subprocess", "COM3", "/dev/mtd",
            "flash_erase", "spi_flash write",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
