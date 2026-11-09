#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f150_5g_autostart_enable_from_f149 as f150  # noqa: E402


class F150AutostartEnableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f150.SRC_BUILD / f"{f150.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f150.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_only_feature_hash_manifest_and_padding_can_change(self) -> None:
        allowed = set(f150.FEATURE_ENTRIES) | {engine.HASHES_ENTRY, engine.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(set(f150.FEATURE_ENTRIES).issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_both_feature_files_are_enabled(self) -> None:
        for entry in f150.FEATURE_ENTRIES:
            self.assertEqual(self.old_map[entry], f150.INACTIVE_FEATURE)
            self.assertEqual(self.new_map[entry], f150.ACTIVE_FEATURE)

    def test_driver_pair_and_start_script_are_unchanged(self) -> None:
        for entry in (
            engine.QDRV_ENTRY,
            engine.WLAN_ENTRY,
            engine.START_ENTRY,
            engine.DRIVER_CONTRACT_ENTRY,
        ):
            self.assertEqual(self.old_map[entry], self.new_map[entry])


if __name__ == "__main__":
    unittest.main(verbosity=2)
