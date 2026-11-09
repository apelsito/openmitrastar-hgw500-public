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
CONTRACT = ROOT / "tools/qtn_5g_v61_scheduler_contract.py"
RUNNER = ROOT / "tools/run_qtn_w3_tx7_client_traffic.py"
PRODUCT_ROOTFS = ROOT / "work/mission-state/w4-rootfs-product/rootfs"

spec = importlib.util.spec_from_file_location("qtn_v61_contract", CONTRACT)
assert spec and spec.loader
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)

runner_spec = importlib.util.spec_from_file_location("qtn_runner", RUNNER)
assert runner_spec and runner_spec.loader
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)


class Qtn5gV61SchedulerContractTests(unittest.TestCase):
    def test_inputs_are_exact_v6_and_offline_only(self) -> None:
        manifest = contract.verify_inputs()
        self.assertEqual(contract.QDRV_SHA256, manifest["artifacts"]["qdrv"]["sha256"])
        self.assertEqual("RAM-ONLY-INSTRUMENTATION-NO-FLASH", manifest["classification"])
        self.assertFalse(manifest["flash"])
        self.assertFalse(manifest["mtd"])
        self.assertFalse(manifest["bootenv"])
        self.assertFalse(manifest["hardware_tested"])

    def test_runner_adapter_accepts_v6_artifact_with_profile_separation(self) -> None:
        manifest = contract.apply_to_runner(runner)
        self.assertEqual(contract.QDRV_SHA256, runner.QDRV_SHA256)
        self.assertEqual((contract.QDRV, contract.QDRV_SHA256), runner.SAFE_MODULES["qdrv.ko"])
        self.assertEqual((contract.START, contract.START_SHA256), runner.SAFE_START)
        self.assertEqual((contract.STOP, contract.STOP_SHA256), runner.SAFE_STOP)
        self.assertEqual(contract.QDRV_PROFILE_SHA256, runner.QDRV_PROFILE_SHA256)
        self.assertNotEqual(runner.QDRV_PROFILE_SHA256, runner.QDRV_SHA256)
        self.assertTrue(manifest["wrapper_acceptance"]["profile_separation_required"])

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
                self.assertEqual(contract.QDRV_PROFILE_SHA256, payload["qdrv_profile_sha256"])
                self.assertFalse(payload["product_integration"]["enabled_service"])
                self.assertFalse(payload["safety"]["flash"])
                manifests.append(payload)
            self.assertEqual(manifests[0], manifests[1])

    def test_capture_minimum_closes_the_known_txpath_gap(self) -> None:
        stages = [item["stage"] for item in contract.capture_minimum()]
        for stage in (
            "capture-ready",
            "qdrv-load-begin",
            "enqueue",
            "enqueue-result",
            "dequeue-ready",
            "hardstart",
            "desc-ready",
            "mailbox-enter",
            "mailbox-published",
            "txdone",
            "rollback-or-recovery",
        ):
            self.assertIn(stage, stages)
        gates = "\n".join(item["gate"] for item in contract.capture_minimum())
        self.assertIn("same skb", gates)
        self.assertIn("same hd_pa", gates)

    def test_product_rootfs_does_not_autostart_v6_diagnostic(self) -> None:
        if not PRODUCT_ROOTFS.exists():
            self.skipTest("product rootfs not staged in this checkout")
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in PRODUCT_ROOTFS.rglob("*")
            if path.is_file() and path.stat().st_size < 200_000
        )
        self.assertNotIn("qdrv-v6-scheduler-diag.ko", text)
        self.assertNotIn("Q3_RADIO5_QDRV_V6_SCHEDULER_DIAG", text)
        self.assertNotIn("om-radio5-start-v6-scheduler-diag", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
