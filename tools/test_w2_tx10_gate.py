#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools/audit_w2_tx10_candidate.py"
VERIFY = ROOT / "tools/verify_w2_tx10_boot_evidence.py"
COLLECT = ROOT / "tools/collect_w2_tx10_boot_evidence.ps1"
GATE = ROOT / "tools/run_w2_2g_tx10_gate.ps1"
LANE = Path(os.environ.get("OM_W2_2G_LANE", ROOT / "work/mission-state/w2-2g-parity-tx10-controls-v1"))
BUILD = LANE / "build"
EXPECTED_BOOT_CLASSIFICATION = os.environ.get(
    "OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION",
    "RAM-ONLY-TX10-LIVE-CLIENT-GATE-NO-FLASH",
)


def expected_image() -> dict:
    manifest_path = BUILD / "manifest.json"
    if manifest_path.is_file():
        artifact = json.loads(manifest_path.read_text(encoding="utf-8"))["artifacts"]["tftp_copy"]
        return {
            "path": f"work/tftp/omvl/{artifact['file']}",
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
        }
    return {
        "path": "work/tftp/omvl/linux510-w2-2g-parity-tx10-controls-v1-RAM-TEST-NO-FLASH.bin",
        "sha256": "998510e1aeabef6e51f953c33533a9b714251dbb5b52062d5eaa112aa431e7ee",
        "bytes": 4331206,
    }


def valid_evidence() -> dict:
    return {
        "schema": "openmitrastar.w2-2g-client-evidence/v1",
        "classification": EXPECTED_BOOT_CLASSIFICATION,
        "image": expected_image(),
        "mutations": False,
        "flash": False,
        "hostapd_stable": True,
        "bridge_eth0_wlan0": True,
        "irq28_progress": True,
        "netdev_errors_delta": 0,
        "no_kernel_oops": True,
        "observed": {
            "boot_state": "ready",
            "radio_state": "ready",
            "hostapd_state": "ENABLED",
            "ssid": "OpenMitraStar-2G-DIAG",
            "channel": 1,
            "bridge_members": ["eth0", "wlan0"],
            "irq20_progress": True,
            "irq28_before": 10,
            "irq28_after": 11,
            "safety_findings": [],
            "txbd_layout": {f"q{i}": f"stride32 {'data' if i < 4 else 'preserved'} compact=1" for i in range(9)},
        },
    }


class Tx10GateTests(unittest.TestCase):
    def test_candidate_audit_passes(self) -> None:
        proc = subprocess.run([sys.executable, str(AUDIT)], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["image"]["sha256"], expected_image()["sha256"])
        self.assertEqual(report["image"]["bytes"], expected_image()["bytes"])
        self.assertTrue(report["slot"]["fits"])
        self.assertFalse(report["flash_supported"])
        self.assertFalse(report["hardware_actions"])

    def test_gate_is_locked_plan_only(self) -> None:
        proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(GATE)], cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM2G_TX10_GATE_PLAN_PASS=1", proc.stdout)
        self.assertIn("OM2G_TX10_EXECUTION_LOCKED_UNTIL_EXACT_RAM_BOOT_EVIDENCE=1", proc.stdout)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_collector_is_locked_plan_only(self) -> None:
        proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COLLECT)], cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX10_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1", proc.stdout)
        self.assertIn("OMTX10_BOOT_EVIDENCE_COLLECTION_LOCKED_UNTIL_ACK=1", proc.stdout)

    def test_verifier_accepts_exact_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boot.json"
            path.write_text(json.dumps(valid_evidence()), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(VERIFY), str(path)], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["ok"])

    def test_verifier_rejects_wrong_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boot.json"
            evidence = valid_evidence()
            evidence["image"]["sha256"] = "0" * 64
            path.write_text(json.dumps(evidence), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(VERIFY), str(path)], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("image.sha256", json.loads(proc.stdout)["failed_checks"])

    def test_wrappers_have_no_boot_or_flash_path(self) -> None:
        combined = GATE.read_text(encoding="utf-8") + COLLECT.read_text(encoding="utf-8")
        self.assertNotIn("COM3", combined)
        self.assertNotIn("bootm", combined.lower())
        self.assertNotIn("flash_erase", combined.lower())
        self.assertNotIn("fw_setenv", combined.lower())


if __name__ == "__main__":
    unittest.main()
