#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "validate_router_lyoko_telemetry_contract.py"
CONTRACT = ROOT / "work" / "mission-state" / "router-lyoko-v0" / "telemetry-contract.json"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoTelemetryContractTests(unittest.TestCase):
    def write_mutated(self, mutator) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        mutator(payload)
        path = Path(tmp.name) / "telemetry-contract.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def test_current_contract_passes(self) -> None:
        proc = run_validator()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["schema"], "router-lyoko.telemetry-contract-guard/v1")
        self.assertEqual(report["classification"], "READONLY-TELEMETRY-CONTRACT-GUARD-NO-HARDWARE")
        self.assertGreaterEqual(report["runtime_fields"], 5)

    def test_rejects_invalid_freshness_window(self) -> None:
        path = self.write_mutated(
            lambda payload: payload["refresh_policy"].update(
                {"fresh_after_seconds": 30, "stale_after_seconds": 15}
            )
        )
        proc = run_validator("--contract", str(path))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("fresh_after_seconds must be lower", proc.stderr)

    def test_rejects_write_enabled_safety_flag(self) -> None:
        path = self.write_mutated(lambda payload: payload["safety"].update({"flash_write": True}))
        proc = run_validator("--contract", str(path))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("safety flag must be false: flash_write", proc.stderr)

    def test_rejects_static_mission_data_promoted_to_hardware_proof(self) -> None:
        def mutate(payload) -> None:
            field = next(item for item in payload["runtime_fields"] if item["path"] == "mission_data.*")
            field["hardware_proof"] = True

        path = self.write_mutated(mutate)
        proc = run_validator("--contract", str(path))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("runtime field mission_data.* must be hardware_proof=false", proc.stderr)

    def test_rejects_wrong_runtime_endpoint(self) -> None:
        path = self.write_mutated(lambda payload: payload.update({"runtime_endpoint": "/api/fake-lyoko"}))
        proc = run_validator("--contract", str(path))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("runtime_endpoint must be /api/lyoko", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
