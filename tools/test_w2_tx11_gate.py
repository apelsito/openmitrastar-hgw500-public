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
VERIFY = ROOT / "tools/verify_w2_tx10_boot_evidence.py"
COLLECT = ROOT / "tools/collect_w2_tx11_boot_evidence.ps1"
GATE = ROOT / "tools/run_w2_2g_tx11_gate.ps1"

SEALED = {
    "lane": ROOT / "work/mission-state/w2-2g-parity-tx11-green-boot-controls-v1",
    "name": "linux510-w2-2g-parity-tx11-green-boot-controls-v1-RAM-TEST-NO-FLASH.bin",
    "sha256": "0ba758b8f10fb7f16237d0b21b1a489bb5895106698b3155bb3d41dc218cf95a",
    "bytes": "4331749",
    "classification": "RAM-ONLY-W2-2G-PARITY-TX11-GREEN-BOOT-CONTROLS-NO-FLASH",
    "profile": "W2_2G_TX11_GREEN_BOOT_CONTROLS_OPEN_DIAG",
    "variant": "TX11_GREEN_BOOT_CONTROLS",
    "boot_classification": "RAM-ONLY-TX11_GREEN_BOOT_CONTROLS-LIVE-CLIENT-GATE-NO-FLASH",
    "boot_token": "RAM-ONLY-TX11_GREEN_BOOT_CONTROLS",
}

FAST = {
    "lane": ROOT / "work/mission-state/w2-2g-parity-tx11-fast-smoke-v1",
    "name": "linux510-w2-2g-parity-tx11-fast-smoke-v1-RAM-TEST-NO-FLASH.bin",
    "sha256": "66982a0930ded5fba794daf77fc9b1a1eeee89e98e9cf0ebe9a0c3e4d356678b",
    "bytes": "4331007",
    "classification": "RAM-ONLY-W2-2G-PARITY-TX11-FAST-SMOKE-NO-FLASH",
    "profile": "W2_2G_TX11_FAST_SMOKE_OPEN_DIAG",
    "variant": "TX11_FAST_SMOKE",
    "boot_classification": "RAM-ONLY-TX11_FAST_SMOKE-LIVE-CLIENT-GATE-NO-FLASH",
    "boot_token": "RAM-ONLY-TX11_FAST_SMOKE",
}


def env_for(candidate: dict[str, object]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "OM_W2_2G_LANE": str(candidate["lane"]),
            "OM_W2_2G_TFTP": str(ROOT / "work/tftp/omvl" / str(candidate["name"])),
            "OM_W2_2G_EXPECTED_IMAGE_NAME": str(candidate["name"]),
            "OM_W2_2G_EXPECTED_IMAGE_SHA256": str(candidate["sha256"]),
            "OM_W2_2G_EXPECTED_IMAGE_BYTES": str(candidate["bytes"]),
            "OM_W2_2G_CLASSIFICATION": str(candidate["classification"]),
            "OM_W2_2G_PROFILE": str(candidate["profile"]),
            "OM_W2_2G_IMAGE_VARIANT": str(candidate["variant"]),
            "OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION": str(candidate["boot_classification"]),
            "OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN": str(candidate["boot_token"]),
            "OM_W2_2G_REALTEK_BUNDLE": str(
                ROOT
                / "outputs/kernel-port/realtek-loop/w2-tx10-rx-signal-safe-v2-RAM-ONLY-NO-FLASH"
            ),
        }
    )
    return env


def valid_evidence(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "openmitrastar.w2-2g-client-evidence/v1",
        "classification": candidate["boot_classification"],
        "image": {
            "path": f"work/tftp/omvl/{candidate['name']}",
            "sha256": candidate["sha256"],
            "bytes": int(str(candidate["bytes"])),
        },
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
            "txbd_layout": {
                f"q{i}": f"stride32 {'data' if i < 4 else 'preserved'} compact=1"
                for i in range(9)
            },
        },
    }


class Tx11GateTests(unittest.TestCase):
    def test_sealed_gate_is_locked_plan_only(self) -> None:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(GATE),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env=env_for(SEALED),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM2G_TX11_GATE_PLAN_PASS=1", proc.stdout)
        self.assertIn("OM2G_TX11_EXECUTION_LOCKED_UNTIL_EXACT_RAM_BOOT_EVIDENCE=1", proc.stdout)
        self.assertIn(str(SEALED["name"]), proc.stdout)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_fast_gate_is_locked_plan_only(self) -> None:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(GATE),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env=env_for(FAST),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM2G_TX11_GATE_PLAN_PASS=1", proc.stdout)
        self.assertIn(str(FAST["name"]), proc.stdout)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_collector_is_locked_plan_only(self) -> None:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(COLLECT),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env=env_for(SEALED),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1", proc.stdout)
        self.assertIn("OMTX11_BOOT_EVIDENCE_COLLECTION_LOCKED_UNTIL_ACK=1", proc.stdout)
        self.assertIn(str(SEALED["name"]), proc.stdout)

    def test_verifier_accepts_tx11_token_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boot.json"
            path.write_text(json.dumps(valid_evidence(SEALED)), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(VERIFY), str(path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                env=env_for(SEALED),
            )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["ok"])

    def test_wrappers_have_no_boot_or_flash_path(self) -> None:
        combined = GATE.read_text(encoding="utf-8") + COLLECT.read_text(encoding="utf-8")
        self.assertNotIn("COM3", combined)
        self.assertNotIn("bootm", combined.lower())
        self.assertNotIn("flash_erase", combined.lower())
        self.assertNotIn("fw_setenv", combined.lower())


if __name__ == "__main__":
    unittest.main()
