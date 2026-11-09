#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools/audit_w2_tx9_candidate.py"
VERIFY_BOOT = ROOT / "tools/verify_w2_tx9_boot_evidence.py"
COLLECT_BOOT = ROOT / "tools/collect_w2_tx9_boot_evidence.ps1"
WRAPPER = ROOT / "tools/run_w2_2g_tx9_gate.ps1"


def valid_boot_evidence() -> dict:
    return {
        "schema": "openmitrastar.w2-2g-client-evidence/v1",
        "classification": "RAM-ONLY-TX9-LIVE-CLIENT-GATE-NO-FLASH",
        "image": {
            "path": "work/tftp/omvl/linux510-w2-2g-parity-tx9-global32-rx-unaligned-v1-RAM-TEST-NO-FLASH.bin",
            "sha256": "cf101c61314a446203b3e581d00f6b32b3111bfd81bc6c2d178f526cd5c1da8a",
            "bytes": 4329980,
        },
        "associated": False,
        "authorized": False,
        "bridge_eth0_wlan0": True,
        "flash": False,
        "hostapd_stable": True,
        "irq28_progress": True,
        "mutations": False,
        "netdev_errors_delta": 0,
        "no_kernel_oops": True,
        "observed": {
            "bridge_members": ["eth0", "wlan0"],
            "channel": 1,
            "hostapd_state": "ENABLED",
            "irq20_after": 120,
            "irq20_before": 100,
            "irq20_progress": True,
            "irq28_after": 250,
            "irq28_before": 200,
            "radio_state": "ready",
            "safety_findings": [],
            "ssid": "OpenMitraStar-2G-DIAG",
            "txbd_layout": {f"q{idx}": "stride32 preserved compact=1" for idx in range(9)},
        },
    }


class Tx9GateTests(unittest.TestCase):
    def test_candidate_audit_passes_exact_current_artifact(self) -> None:
        proc = subprocess.run([sys.executable, str(AUDIT)], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["schema"], "openmitrastar.w2-tx9-candidate-audit/v1")
        self.assertEqual(report["image"]["sha256"], "cf101c61314a446203b3e581d00f6b32b3111bfd81bc6c2d178f526cd5c1da8a")
        self.assertEqual(report["image"]["bytes"], 4329980)
        self.assertTrue(report["slot"]["fits"])
        self.assertEqual(report["bootbase_contract"], "PASS")
        self.assertFalse(report["candidate_eligible"])
        self.assertFalse(report["flash_supported"])
        self.assertFalse(report["hardware_actions"])

    def test_wrapper_defaults_to_locked_plan_only(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WRAPPER)],
            cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM2G_TX9_GATE_PLAN_PASS=1", proc.stdout)
        self.assertIn("OM2G_TX9_EXECUTION_LOCKED_UNTIL_EXACT_RAM_BOOT_EVIDENCE=1", proc.stdout)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_boot_evidence_collector_defaults_to_locked_plan_only(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COLLECT_BOOT)],
            cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX9_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1", proc.stdout)
        self.assertIn("OMTX9_BOOT_EVIDENCE_COLLECTION_LOCKED_UNTIL_ACK=1", proc.stdout)
        self.assertNotIn("OMTX9_BOOT_EVIDENCE_VERIFIED=1", proc.stdout)

    def test_boot_evidence_collector_execute_requires_ack(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COLLECT_BOOT), "-ExecuteCollection"],
            cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("TX9 boot evidence collection requires exact -AckReadOnly", proc.stdout + proc.stderr)
        self.assertNotIn("OMTX9_BOOT_EVIDENCE_VERIFIED=1", proc.stdout)

    def test_execute_requires_exact_ack(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WRAPPER), "-ExecuteGate"],
            cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("TX9 execution requires exact -AckRamOnly", proc.stdout + proc.stderr)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_execute_rejects_wrong_boot_evidence_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "boot.json"
            payload = valid_boot_evidence()
            payload["image"]["sha256"] = "0" * 64
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            proc = subprocess.run(
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(WRAPPER),
                    "-ExecuteGate",
                    "-AckRamOnly", "OPENMITRASTAR_TX9_GLOBAL32_RX_UNALIGNED_CLIENT_GATE_RAM_ONLY",
                    "-Tx9BootEvidenceJson", str(evidence),
                ],
                cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("TX9 boot evidence verifier failed", proc.stdout + proc.stderr)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_boot_evidence_verifier_accepts_exact_tx9_boot_without_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "boot.json"
            evidence.write_text(json.dumps(valid_boot_evidence()), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(VERIFY_BOOT), str(evidence)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "TX9_BOOT_EVIDENCE_ACCEPTED")

    def test_boot_evidence_verifier_rejects_tx7_or_missing_global32_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "boot.json"
            payload = valid_boot_evidence()
            payload["classification"] = "RAM-ONLY-TX7-LIVE-CLIENT-GATE-NO-FLASH"
            payload["image"]["path"] = "work/tftp/omvl/linux510-w2-2g-parity-tx7-hybrid32-v1-RAM-TEST-NO-FLASH.bin"
            payload["observed"]["txbd_layout"]["q4"] = "stride64 beacon compact=0"
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(VERIFY_BOOT), str(evidence)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertFalse(report["ok"])
        self.assertIn("classification.tx9", report["failed_checks"])
        self.assertIn("txbd.q4.stride32", report["failed_checks"])

    def test_wrapper_source_has_no_boot_or_flash_path(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("run_w2_2g_candidate_gate.ps1", text)
        self.assertIn("audit_w2_tx9_candidate.py", text)
        self.assertIn("verify_w2_tx9_boot_evidence.py", text)
        self.assertIn("ExecuteGate", text)
        self.assertNotIn("COM3", text)
        self.assertNotIn("bootm", text.lower())
        self.assertNotIn("flash_erase", text.lower())
        self.assertNotIn("fw_setenv", text.lower())

    def test_collector_source_has_no_com_reboot_or_flash_path(self) -> None:
        text = COLLECT_BOOT.read_text(encoding="utf-8")
        self.assertIn("collect_w2_2g_client_gate.py", text)
        self.assertIn("verify_w2_tx9_boot_evidence.py", text)
        self.assertIn("ExecuteCollection", text)
        self.assertNotIn("COM3", text)
        self.assertNotIn("bootm", text.lower())
        self.assertNotIn("flash_erase", text.lower())
        self.assertNotIn("fw_setenv", text.lower())


if __name__ == "__main__":
    unittest.main()
