#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tools/qtn_5g_v62_scheduler_contract.py"
RUNNER = ROOT / "tools/run_qtn_w3_tx7_client_traffic.py"

spec = importlib.util.spec_from_file_location("qtn_v62_contract", CONTRACT)
assert spec and spec.loader
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)

runner_spec = importlib.util.spec_from_file_location("qtn_runner", RUNNER)
assert runner_spec and runner_spec.loader
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)


class Qtn5gV62SchedulerContractTests(unittest.TestCase):
    def test_inputs_are_exact_v62_uafsafe_and_offline_only(self) -> None:
        manifest = contract.verify_inputs()
        self.assertEqual(
            "5b9ae80e5121c4b00965ce4716ad80285f1b599e29845e8efbf938a79600df35",
            contract.QDRV_SHA256,
        )
        self.assertEqual(
            contract.QDRV_SHA256,
            manifest["artifacts"]["qdrv-v6.2-scheduler-diag-uafsafe.ko"]["sha256"],
        )
        self.assertEqual("RAM-ONLY-INSTRUMENTATION-NO-FLASH", manifest["classification"])
        self.assertFalse(manifest["safety"]["flash"])
        self.assertFalse(manifest["safety"]["mtd"])
        self.assertFalse(manifest["safety"]["bootenv"])
        self.assertIn("use-after-free", manifest["single_change"])

    def test_runner_adapter_accepts_v62_artifact_with_profile_separation(self) -> None:
        manifest = contract.apply_to_runner(runner)
        self.assertEqual(contract.QDRV_SHA256, runner.QDRV_SHA256)
        self.assertEqual((contract.QDRV, contract.QDRV_SHA256), runner.SAFE_MODULES["qdrv.ko"])
        self.assertEqual((contract.START, contract.START_SHA256), runner.SAFE_START)
        self.assertEqual((contract.STOP, contract.STOP_SHA256), runner.SAFE_STOP)
        self.assertEqual(contract.QDRV_PROFILE_SHA256, runner.QDRV_PROFILE_SHA256)
        self.assertNotEqual(runner.QDRV_PROFILE_SHA256, runner.QDRV_SHA256)
        self.assertEqual("openmitrastar.qtn-5g-v6.2-scheduler-contract/v1", manifest["schema"])

    def test_contract_build_is_reproducible_and_hash_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            manifests = []
            for directory in (first, second):
                proc = subprocess.run(
                    [sys.executable, str(CONTRACT), "--output-dir", directory],
                    cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
                )
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                payload = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(contract.QDRV_SHA256, payload["qdrv_artifact_sha256"])
                self.assertFalse(payload["product_integration"]["enabled_service"])
                self.assertFalse(payload["safety"]["flash"])
                manifests.append(payload)
            self.assertEqual(manifests[0], manifests[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
