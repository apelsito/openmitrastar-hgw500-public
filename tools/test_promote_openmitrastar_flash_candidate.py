#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
SCRIPT = WORKSPACE / "tools/promote_openmitrastar_flash_candidate.py"
EXPECTED_SHA = "96e8e7ac1c75e458bee7538ba7a525890709513ef7c189f7078386f5cc80db1f"
FOUNDATION_SHA = "4bca4d3c97e0d7d76f6599bc9c87d02dc571c027971b2cdf7cbfa9639000e081"
FOUNDATION_CONTRACT = WORKSPACE / "work/mission-state/F5_FOUNDATION_FLASH_CANDIDATE_INPUT_CONTRACT.json"
FOUNDATION_BUILD = WORKSPACE / "work/mission-state/f5-foundation-nowdt/build"
FOUNDATION_BASENAME = "openmitrastar-f5-foundation-nowdt-v1"


class PromotionTests(unittest.TestCase):
    def test_promotes_exact_artifact_without_runtime_attestations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workspace",
                    str(WORKSPACE),
                    "--candidate-dir",
                    str(destination),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OMF2_PROMOTION_PASS", result.stdout)
            self.assertIn("flash_ready=false", result.stdout)
            candidate = destination / "openmitrastar-linux510-product-webformat.bin"
            manifest_path = destination / "manifest.json"
            self.assertTrue(candidate.is_file())
            self.assertTrue(manifest_path.is_file())
            observed = hashlib.sha256(candidate.read_bytes()).hexdigest()
            self.assertEqual(observed, EXPECTED_SHA)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["candidate_eligible"])
            self.assertFalse(manifest["flash_ready"])
            self.assertEqual(manifest["artifact"]["sha256"], EXPECTED_SHA)
            self.assertEqual(
                set(manifest["runtime_gates"].values()),
                {"PENDING"},
            )
            serialized = manifest_path.read_text(encoding="utf-8")
            self.assertNotIn("OM_PRODUCT_PRIVATE_PSK", serialized)

    def test_script_has_no_hardware_or_flash_execution_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "import serial",
            "import socket",
            "import subprocess",
            "/dev/mtd",
            "flash_erase",
            "mtd write",
        ):
            self.assertNotIn(forbidden, source)

    def test_promotes_management_only_foundation_without_psk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workspace",
                    str(WORKSPACE),
                    "--contract",
                    str(FOUNDATION_CONTRACT),
                    "--build-dir",
                    str(FOUNDATION_BUILD),
                    "--basename",
                    FOUNDATION_BASENAME,
                    "--candidate-dir",
                    str(destination),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            candidate = destination / "openmitrastar-linux510-f5-foundation-webformat.bin"
            manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256(candidate.read_bytes()).hexdigest(), FOUNDATION_SHA)
            self.assertEqual(manifest["classification"], "PERSISTENT-FOUNDATION-FLASH-CANDIDATE")
            self.assertEqual(manifest["profile"], "F5_FOUNDATION")
            self.assertEqual(manifest["scope"], "MANAGEMENT-ONLY")
            self.assertFalse(manifest["security"]["psk_bundled"])
            self.assertTrue(manifest["capabilities"]["cgi_management"])
            self.assertEqual(manifest["capabilities"]["management_ipv4"], "192.168.1.90")
            self.assertEqual(manifest["capabilities"]["radio_policy"], "fail-closed-no-credentials")
            self.assertFalse(manifest["completion_claims"]["full_product"])
            self.assertFalse(manifest["completion_claims"]["oem_parity_100"])

    def test_foundation_build_cannot_use_full_product_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--workspace",
                    str(WORKSPACE),
                    "--build-dir",
                    str(FOUNDATION_BUILD),
                    "--basename",
                    FOUNDATION_BASENAME,
                    "--candidate-dir",
                    temporary,
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("selected profile", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
