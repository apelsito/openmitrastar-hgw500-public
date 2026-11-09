#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f149_5g_persistent_wlan_contract_from_f148 as f149  # noqa: E402


class F149PersistentWlanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f149.SRC_BUILD / f"{f149.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f149.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_only_start_hash_manifest_and_padding_change(self) -> None:
        allowed = {engine.START_ENTRY, engine.HASHES_ENTRY, engine.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertEqual(changed, {engine.START_ENTRY, engine.HASHES_ENTRY})
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_modules_and_driver_contract_are_byte_identical(self) -> None:
        for entry, expected in (
            (engine.QDRV_ENTRY, f149.QDRV_SHA),
            (engine.WLAN_ENTRY, f149.WLAN_SHA),
        ):
            self.assertEqual(self.old_map[entry], self.new_map[entry])
            self.assertEqual(hashlib.sha256(self.new_map[entry]).hexdigest(), expected)
        self.assertEqual(
            self.old_map[engine.DRIVER_CONTRACT_ENTRY],
            self.new_map[engine.DRIVER_CONTRACT_ENTRY],
        )

    def test_start_uses_rebuilt_wlan_hash_in_profile_override(self) -> None:
        start = self.new_map[engine.START_ENTRY].decode("ascii")
        self.assertIn(f"expected_wlan_sha={f149.WLAN_SHA}", start)
        self.assertNotIn(f"expected_wlan_sha={f149.OLD_WLAN_SHA}", start)
        hashes = self.new_map[engine.HASHES_ENTRY].decode("ascii")
        self.assertIn(hashlib.sha256(self.new_map[engine.START_ENTRY]).hexdigest(), hashes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
