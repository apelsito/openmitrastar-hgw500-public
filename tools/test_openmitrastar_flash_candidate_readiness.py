#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/openmitrastar_flash_candidate_readiness.py"
JSON_OUT = ROOT / "work/mission-state/F2_FLASH_CANDIDATE_READINESS.json"
MD_OUT = ROOT / "work/mission-state/F2_FLASH_CANDIDATE_READINESS.md"
PROMOTER = ROOT / "tools/promote_openmitrastar_flash_candidate.py"
FOUNDATION_CONTRACT = ROOT / "work/mission-state/F5_FOUNDATION_FLASH_CANDIDATE_INPUT_CONTRACT.json"
FOUNDATION_BUILD = ROOT / "work/mission-state/f5-foundation-nowdt/build"


class CandidateReadinessTests(unittest.TestCase):
    def run_tool(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--workspace",
                str(ROOT),
                "--json-out",
                str(JSON_OUT),
                "--md-out",
                str(MD_OUT),
                *extra,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_current_incremental_assessment_is_complete_but_not_eligible(self) -> None:
        proc = self.run_tool()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(JSON_OUT.read_text(encoding="utf-8"))
        self.assertTrue(report["assessment_complete"])
        self.assertFalse(report["candidate_eligible"])
        self.assertFalse(report["flash_ready"])
        self.assertFalse(report["audit_replayed"])
        self.assertTrue(report["cached_f2_reused"])
        gates = {gate["id"]: gate for gate in report["gates"]}
        self.assertTrue(gates["cached-f2-32-of-32"]["passed"])
        self.assertIn("audit_replayed=false", gates["cached-f2-32-of-32"]["detail"])
        self.assertTrue(gates["ram-kernel-component"]["passed"])
        self.assertFalse(gates["realtek-ram-bundle"]["blocking"])
        self.assertFalse(gates["product-rootfs-component"]["blocking"])
        self.assertTrue(gates["realtek-probe-runtime-evidence"]["passed"])
        self.assertTrue(gates["integrated-persistent-candidate"]["passed"])
        self.assertTrue(gates["candidate-manifest-contract"]["passed"])
        self.assertFalse(gates["fresh-current-flash-read"]["passed"])
        self.assertFalse(gates["same-candidate-ram-equivalence"]["passed"])
        self.assertEqual(len(report["missing_inputs"]), 2)

    def test_strict_mode_fails_closed(self) -> None:
        proc = self.run_tool("--strict")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("candidate_eligible=false", proc.stdout)

    def test_script_has_no_hardware_or_flash_runtime_imports(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "import subprocess",
            "import socket",
            "import serial",
            "paramiko",
            "/dev/mtd",
            "flashcp",
            "saveenv",
            "flwrite",
        ):
            self.assertNotIn(forbidden, source)

    def prepare_foundation(self, temporary: Path) -> tuple[Path, Path, Path]:
        candidate_dir = temporary / "candidate"
        contract = json.loads(FOUNDATION_CONTRACT.read_text(encoding="utf-8"))
        contract["required_candidate_inputs"]["directory"] = str(candidate_dir)
        contract_path = temporary / "foundation-contract.json"
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        promoted = subprocess.run(
            [
                sys.executable,
                str(PROMOTER),
                "--workspace",
                str(ROOT),
                "--contract",
                str(contract_path),
                "--build-dir",
                str(FOUNDATION_BUILD),
                "--basename",
                "openmitrastar-f5-foundation-nowdt-v1",
                "--candidate-dir",
                str(candidate_dir),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(promoted.returncode, 0, promoted.stdout + promoted.stderr)
        return contract_path, candidate_dir, temporary / "readiness.json"

    def run_foundation_readiness(self, contract: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--workspace",
                str(ROOT),
                "--contract",
                str(contract),
                "--json-out",
                str(output),
                "--md-out",
                str(output.with_suffix(".md")),
            ],
            text=True,
            capture_output=True,
        )

    def test_foundation_profile_is_distinct_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temporary = Path(raw)
            contract, _candidate_dir, output = self.prepare_foundation(temporary)
            proc = self.run_foundation_readiness(contract, output)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["profile"], "openmitrastar-linux510-f5-foundation-management-v1")
            self.assertFalse(report["candidate_eligible"])
            gates = {gate["id"]: gate for gate in report["gates"]}
            self.assertTrue(gates["safety-rollback-preserved"]["passed"])
            self.assertTrue(gates["integrated-persistent-candidate"]["passed"])
            self.assertTrue(gates["candidate-manifest-contract"]["passed"])
            self.assertTrue(gates["candidate-profile-boundary"]["passed"])
            self.assertFalse(gates["fresh-current-flash-read"]["passed"])
            self.assertFalse(gates["same-candidate-ram-equivalence"]["passed"])
            self.assertEqual(
                {item["gate"] for item in report["missing_inputs"]},
                {"fresh-current-flash-read", "same-candidate-ram-equivalence"},
            )

    def test_foundation_cannot_masquerade_as_full_product(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temporary = Path(raw)
            contract, candidate_dir, output = self.prepare_foundation(temporary)
            manifest_path = candidate_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["capabilities"]["full_product"] = True
            manifest["completion_claims"]["full_product"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            proc = self.run_foundation_readiness(contract, output)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            gates = {gate["id"]: gate for gate in report["gates"]}
            self.assertFalse(gates["candidate-profile-boundary"]["passed"])
            self.assertIn("full_product", gates["candidate-profile-boundary"]["detail"])
            self.assertFalse(report["candidate_eligible"])

    def test_foundation_current_candidate_has_complete_blocking_contract(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "foundation-current-readiness.json"
            proc = self.run_foundation_readiness(FOUNDATION_CONTRACT, output)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["candidate_eligible"])
            self.assertFalse(report["flash_ready"])
            self.assertEqual(report["missing_inputs"], [])
            gates = {gate["id"]: gate for gate in report["gates"]}
            for gate in gates.values():
                if gate["blocking"]:
                    self.assertTrue(gate["passed"], gate)
            self.assertTrue(gates["fresh-current-flash-read"]["passed"])
            self.assertTrue(gates["same-candidate-ram-equivalence"]["passed"])


if __name__ == "__main__":
    unittest.main()
