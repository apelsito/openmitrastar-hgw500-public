#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(
    os.environ.get(
        "REALTEK_TX1_BUNDLE",
        ROOT
        / "outputs/kernel-port/realtek-loop/"
        "w2-tx1-publish-barrier-RAM-ONLY-NO-FLASH",
    )
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RealtekTx1BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text())

    def test_ram_only_contract(self) -> None:
        self.assertEqual(self.manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(self.manifest["candidate_eligible"])
        self.assertFalse(self.manifest["safety"]["flash_supported"])
        self.assertFalse(self.manifest["safety"]["router_accessed"])

    def test_experiment_contract(self) -> None:
        experiments = self.manifest["experiments"]
        barrier = experiments["hgw500_tx_dma_wmb"]
        close = experiments["hgw500_tx_close_diag"]
        self.assertFalse(barrier["default"])
        self.assertFalse(close["default"])
        self.assertTrue(barrier["ampdu_unchanged"])
        self.assertTrue(barrier["ack_policy_unchanged"])
        self.assertEqual(
            self.manifest["static_gates"]["tx_complete_trace_bounded"], "PASS"
        )

    def test_upload_hashes(self) -> None:
        for line in (BUNDLE / "UPLOAD_SHA256SUMS").read_text().splitlines():
            expected, relative = line.split(maxsplit=1)
            relative = relative.lstrip("* ")
            path = BUNDLE / relative
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256(path), expected)

    def test_arc_barrier_disassembly(self) -> None:
        text = (BUNDLE / "evidence/rtl92ee_set_desc.disasm.txt").read_text()
        self.assertIn("<rtl92ee_set_desc>", text)
        self.assertRegex(text, r"\bsync\b")

    def test_required_modules_and_order(self) -> None:
        order = (BUNDLE / "LOAD_ORDER.txt").read_text().splitlines()
        self.assertEqual(order[-3:], ["btcoexist.ko", "rtl_pci.ko", "rtl8192ee.ko"])
        for module in order:
            self.assertTrue((BUNDLE / "modules" / module).is_file(), module)


if __name__ == "__main__":
    unittest.main()
