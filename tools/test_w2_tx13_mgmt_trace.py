#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "tools/run_w2_tx13_ram_boot.ps1"
COLLECT = ROOT / "tools/collect_w2_tx13_mgmt_trace.ps1"
IMAGE = ROOT / "work/tftp/omvl/linux510-w2-2g-parity-tx13-lossless-mgmt-trace-v1-RAM-TEST-NO-FLASH.bin"
MANIFEST = ROOT / "work/mission-state/w2-2g-parity-tx13-lossless-mgmt-trace-v1/build/manifest.json"
EXPECTED_SHA256 = "66f9efe41c08c4fecac2b60521b6ec7d37b1390502862dd8cd6e493b6d8239c3"
EXPECTED_BYTES = 4_334_366


def run_ps1(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


class Tx13MgmtTraceTests(unittest.TestCase):
    def test_artifact_and_manifest_are_exactly_bound(self) -> None:
        self.assertEqual(IMAGE.stat().st_size, EXPECTED_BYTES)
        self.assertEqual(hashlib.sha256(IMAGE.read_bytes()).hexdigest(), EXPECTED_SHA256)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["classification"],
            "RAM-ONLY-W2-2G-PARITY-TX13-LOSSLESS-MGMT-TRACE-NO-FLASH",
        )
        self.assertFalse(manifest["flash_supported"])
        self.assertFalse(manifest["candidate_eligible"])
        self.assertTrue(manifest["reproducibility"]["fast_iteration"])
        self.assertEqual(manifest["slot"]["bootbase_contract"], "PASS")
        self.assertTrue(manifest["slot"]["fits"])
        self.assertEqual(manifest["artifacts"]["tftp_copy"]["sha256"], EXPECTED_SHA256)

    def test_ram_boot_is_plan_only_without_exact_ack(self) -> None:
        proc = run_ps1(BOOT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX13_RAM_BOOT_PREFLIGHT_PASS=1 execute=0 flash=0", proc.stdout)
        self.assertIn("OPENMITRASTAR_TX13_RAM_BOOT_ONLY_NO_FLASH", proc.stdout)
        self.assertNotIn("OMTX13_RAM_BOOT_PASS=1", proc.stdout)

    def test_trace_collection_is_plan_only_without_exact_ack(self) -> None:
        proc = run_ps1(COLLECT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("openmitrastar.w2-tx13-mgmt-trace-collection-plan/v1", proc.stdout)
        self.assertIn("OMTX13_MGMT_TRACE_COLLECTION_PLAN_PASS=1", proc.stdout)
        self.assertIn("OPENMITRASTAR_COLLECT_TX13_MGMT_TRACE_READONLY", proc.stdout)
        self.assertNotIn("OMTX13_MGMT_TRACE_COLLECTED=1", proc.stdout)

    def test_execute_paths_reject_missing_ack_before_hardware(self) -> None:
        boot = run_ps1(BOOT, "-Execute")
        self.assertNotEqual(boot.returncode, 0)
        self.assertIn("requires exact -AckRamOnly", boot.stdout + boot.stderr)
        collect = run_ps1(COLLECT, "-ExecuteCollection")
        self.assertNotEqual(collect.returncode, 0)
        self.assertIn("requires exact -AckReadOnly", collect.stdout + collect.stderr)


if __name__ == "__main__":
    unittest.main()
