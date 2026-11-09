#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/openmitrastar_flash_backup_preflight.py"
BASELINE = ROOT / "work/mission-state/F2_FLASH_BACKUP_BASELINE.json"
REPORT = ROOT / "work/mission-state/F2_FLASH_BACKUP_PREFLIGHT.json"


class FlashBackupPreflightTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--workspace", str(ROOT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_backup_audit_passes_real_pinned_dump(self) -> None:
        proc = self.run_tool(
            "--mode",
            "backup-audit",
            "--baseline",
            str(BASELINE),
            "--json-out",
            str(REPORT),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["backup_certified"])
        self.assertFalse(report["flash_ready"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["hardware_access"])
        self.assertFalse(report["flash_commands_present"])
        gates = {item["name"]: item for item in report["gates"]}
        self.assertTrue(gates["physical-image-sha256"]["passed"])
        self.assertTrue(gates["logical-6-is-view-not-physical"]["passed"])
        self.assertTrue(gates["reject-mtd0-mtd6-as-raw-flash"]["passed"])
        self.assertTrue(gates["redundant-environment"]["passed"])
        self.assertTrue(gates["inactive-target-and-rollback-plan"]["passed"])
        self.assertTrue(gates["uart-bootbase-tftp-ramssh-recovery"]["passed"])

    def test_flash_preflight_fails_closed_without_candidate(self) -> None:
        proc = self.run_tool("--mode", "flash-preflight", "--baseline", str(BASELINE))
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["backup_certified"])
        self.assertFalse(report["flash_ready"])
        self.assertFalse(report["post_flash_rollback_executed"])
        candidate_gate = next(
            item for item in report["gates"] if item["name"] == "flash-candidate-pinned-and-eligible"
        )
        self.assertFalse(candidate_gate["passed"])
        current_gate = next(
            item
            for item in report["gates"]
            if item["name"] == "current-read-only-flash-attestation"
        )
        self.assertFalse(current_gate["passed"])

    def test_safety_slot_cannot_be_selected_as_candidate(self) -> None:
        proc = self.run_tool(
            "--mode",
            "backup-audit",
            "--baseline",
            str(BASELINE),
            "--target",
            "linux_safety",
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        plan_gate = next(
            item for item in report["gates"] if item["name"] == "inactive-target-and-rollback-plan"
        )
        self.assertFalse(plan_gate["passed"])

    def test_current_ram_only_artifact_is_rejected_as_persistent_candidate(self) -> None:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        hashes = {
            part["name"]: part["sha256"]
            for part in baseline["partitions"]
            if part["name"] in baseline["flash_plan"]["preserve"]
        }
        attestation = {
            "schema": "openmitrastar.current-flash-read/v1",
            "captured_at": "unit-test-fixture",
            "read_only": True,
            "device": baseline["device"],
            "target_slot": "linux_live",
            "bootcmd": "bootselect",
            "bootselect": "1",
            "partition_sha256": hashes,
        }
        candidate = ROOT / "work/tftp/omvl/linux510-radiohw-pci-probe-webformat.bin"
        manifest = ROOT / "outputs/kernel-port/realtek-loop/current-RAM-ONLY-NO-FLASH/manifest.json"
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current.json"
            current.write_text(json.dumps(attestation), encoding="utf-8")
            proc = self.run_tool(
                "--mode",
                "flash-preflight",
                "--baseline",
                str(BASELINE),
                "--current-read-attestation",
                str(current),
                "--candidate",
                str(candidate),
                "--candidate-manifest",
                str(manifest),
            )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        current_gate = next(
            item
            for item in report["gates"]
            if item["name"] == "current-read-only-flash-attestation"
        )
        candidate_gate = next(
            item for item in report["gates"] if item["name"] == "flash-candidate-pinned-and-eligible"
        )
        self.assertTrue(current_gate["passed"])
        self.assertFalse(candidate_gate["passed"])
        self.assertTrue(report["candidate"]["format_ok"])
        self.assertFalse(report["candidate"]["candidate_eligible"])


if __name__ == "__main__":
    unittest.main()
