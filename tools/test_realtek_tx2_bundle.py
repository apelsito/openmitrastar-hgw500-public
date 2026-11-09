#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/realtek-loop/w2-tx2-compact-txbd-RAM-ONLY-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Tx2BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text())

    def test_hash_manifest(self) -> None:
        for line in (BUNDLE / "SHA256SUMS").read_text().splitlines():
            expected, relative = line.split(maxsplit=1)
            path = BUNDLE / relative.lstrip("* ")
            self.assertTrue(path.is_file(), path)
            self.assertEqual(sha256(path), expected)

    def test_compact_contract(self) -> None:
        experiment = self.manifest["experiments"]["hgw500_txbd_compact32"]
        self.assertFalse(experiment["default"])
        self.assertEqual(experiment["txbd_entry_bytes"], 32)
        self.assertEqual(experiment["txbd_segment_bytes"], 8)
        self.assertEqual(experiment["txbd_segments"], 4)
        self.assertFalse(experiment["forced_reclaim"])
        self.assertEqual(
            experiment["double_free_uaf_guard"],
            "index-equal-hardware-rp-remains-not-closed",
        )

    def test_hotload_scripts_are_gated(self) -> None:
        apply = (BUNDLE / "apply-realtek-tx2").read_text()
        verify = (BUNDLE / "verify-realtek-tx2").read_text()
        rollback = (BUNDLE / "rollback-realtek-tx2").read_text()
        self.assertIn("OPENMITRASTAR_W2_TX2_RAM_ONLY", apply)
        self.assertIn("hgw500_txbd_compact32=1", apply)
        self.assertIn("hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0", apply)
        self.assertIn("OPENMITRASTAR_W2_TX2_VERIFY", verify)
        self.assertIn("OPENMITRASTAR_W2_TX2_ROLLBACK", rollback)
        self.assertIn("OMW2_TX2_ROLLBACK_PASS", rollback)

    def test_module_hashes_match_manifest(self) -> None:
        artifacts = {item["path"]: item for item in self.manifest["artifacts"]}
        for relative in (
            "modules/rtl_pci.ko",
            "modules/rtl8192ee.ko",
            "modules/rtlwifi.ko",
        ):
            path = BUNDLE / relative
            self.assertEqual(sha256(path), artifacts[relative]["sha256"])


if __name__ == "__main__":
    unittest.main()
