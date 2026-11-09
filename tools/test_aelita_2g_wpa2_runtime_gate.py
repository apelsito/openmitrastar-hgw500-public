#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "tools/evaluate_aelita_2g_wpa2_runtime.py"

spec = importlib.util.spec_from_file_location("aelita_2g_eval", EVALUATOR)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def pass_result() -> dict:
    return {
        "execution_error": None,
        "router_mutations": False,
        "flash": False,
        "secret_blob_deleted": True,
        "profile_deleted": True,
        "test": {
            "connected": True,
            "ipv4": {"ipv4": "192.168.1.63", "gateway": "192.168.1.1"},
            "router_ping": {"pass": True},
            "controller_download": {"pass": True, "http_code": 200, "bytes": 290},
            "soak": {
                "requested_seconds": 600,
                "samples": 600,
                "connected_samples": 600,
                "disconnects": 0,
            },
        },
        "restore": {
            "attempted": True,
            "connected": True,
            "ipv4": {"ipv4": "192.168.1.63"},
        },
    }


class Aelita2gRuntimeGateTests(unittest.TestCase):
    def test_good_result_passes_basic_wpa2_gate(self) -> None:
        result = module.evaluate(pass_result())
        self.assertEqual("PASS", result["status"])
        self.assertTrue(result["claims"]["wpa2_association"])
        self.assertTrue(result["claims"]["bidirectional_basic_ip"])
        self.assertEqual("UNVERIFIED", result["claims"]["throughput"])

    def test_short_soak_fails_closed(self) -> None:
        payload = pass_result()
        payload["test"]["soak"]["requested_seconds"] = 60
        result = module.evaluate(payload)
        self.assertIn("soak_duration", result["failures"])

    def test_disconnect_restore_and_secret_cleanup_are_required(self) -> None:
        payload = pass_result()
        payload["test"]["soak"]["disconnects"] = 1
        payload["restore"]["connected"] = False
        payload["secret_blob_deleted"] = False
        result = module.evaluate(payload)
        self.assertIn("soak_disconnects", result["failures"])
        self.assertIn("restore_connected", result["failures"])
        self.assertIn("secret_blob_deleted", result["failures"])

    def test_router_mutation_or_flash_is_fatal(self) -> None:
        payload = pass_result()
        payload["router_mutations"] = True
        payload["flash"] = True
        result = module.evaluate(payload)
        self.assertIn("router_mutations", result["failures"])
        self.assertIn("flash", result["failures"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
