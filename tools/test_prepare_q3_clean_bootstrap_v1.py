#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/prepare_q3_clean_bootstrap_v1.py"
spec = importlib.util.spec_from_file_location("clean_bootstrap", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CleanBootstrapTests(unittest.TestCase):
    def test_accepts_minimal_5g_pass(self) -> None:
        payload = {
            "schema": "openmitrastar.qtn-5g-isolated-l3-evaluation/v1",
            "status": "PASS",
            "network": {
                "direct_bidirectional_icmp": True,
                "main_management_preserved": True,
                "wifi0_in_br0": False,
            },
        }
        self.assertTrue(module.valid_5g_evaluation(payload))

    def test_rejects_bridge_or_management_loss(self) -> None:
        payload = {
            "schema": "openmitrastar.qtn-5g-isolated-l3-evaluation/v1",
            "status": "PASS",
            "network": {
                "direct_bidirectional_icmp": True,
                "main_management_preserved": False,
                "wifi0_in_br0": True,
            },
        }
        self.assertFalse(module.valid_5g_evaluation(payload))

    def test_slot_is_exactly_linux_live_size(self) -> None:
        lock = module.load_json(module.LOCK)
        self.assertEqual(0x7A0000, lock["target"]["slot_bytes"])
        self.assertEqual("mtd4_linux_live", lock["target"]["future_write_target"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
