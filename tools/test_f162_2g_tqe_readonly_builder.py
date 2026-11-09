#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f162_2g_tqe_readonly_from_f157 as f162  # noqa: E402


class F162TqeReadonlyBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f162.SRC_BUILD / f"{f162.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f162.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_replaces_only_switch_tqe_and_integrity_metadata(self) -> None:
        allowed = {
            f162.SWITCH_TQE_ENTRY,
            f162.CONTRACT_ENTRY,
            f162.HASHES_ENTRY,
            f162.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed), changed - allowed)
        self.assertEqual(self.old_map[f162.QDRV_ENTRY], self.new_map[f162.QDRV_ENTRY])
        self.assertEqual(self.old_map[f162.WLAN_ENTRY], self.new_map[f162.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_counter_marker_hash_and_contract_are_exact(self) -> None:
        module = self.new_map[f162.SWITCH_TQE_ENTRY]
        self.assertEqual(hashlib.sha256(module).hexdigest(), f162.NEW_SWITCH_TQE_SHA)
        self.assertIn(b"omtqe-readonly-v1", module)
        contract = self.new_map[f162.CONTRACT_ENTRY].decode("ascii")
        hashes = self.new_map[f162.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"SWITCH_TQE_SHA256={f162.NEW_SWITCH_TQE_SHA}", contract)
        self.assertIn(f162.NEW_SWITCH_TQE_SHA, hashes)
        self.assertNotIn(f162.OLD_SWITCH_TQE_SHA, contract)


if __name__ == "__main__":
    unittest.main(verbosity=2)
