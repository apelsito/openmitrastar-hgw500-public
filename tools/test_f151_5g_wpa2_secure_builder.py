#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f151_5g_wpa2_secure_from_f150 as f151  # noqa: E402


class F151Wpa2SecureBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f151.SRC_BUILD / f"{f151.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f151.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_secure_feature_and_beacon_guard(self) -> None:
        self.assertEqual(self.old_map[f151.OPEN_LAB_ENTRY], f151.OPEN_LAB_ON)
        self.assertEqual(self.new_map[f151.OPEN_LAB_ENTRY], f151.OPEN_LAB_OFF)
        start = self.new_map[engine.START_ENTRY].decode("ascii")
        self.assertNotIn(f151.OLD_GUARD, start)
        self.assertIn(f151.NEW_GUARD, start)
        self.assertIn("wpa=2", start)
        self.assertIn("wpa_key_mgmt=WPA-PSK", start)
        self.assertIn("wpa_pairwise=CCMP", start)
        self.assertIn("psk_result=redacted", start)

    def test_modules_and_topology_script_are_preserved(self) -> None:
        for entry in (engine.QDRV_ENTRY, engine.WLAN_ENTRY):
            self.assertEqual(self.old_map[entry], self.new_map[entry])
        self.assertIn(
            "isolated-l3",
            self.new_map[engine.START_ENTRY].decode("ascii"),
        )

    def test_change_scope_and_fixed_layout(self) -> None:
        allowed = {
            f151.OPEN_LAB_ENTRY,
            engine.START_ENTRY,
            engine.HASHES_ENTRY,
            engine.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue({f151.OPEN_LAB_ENTRY, engine.START_ENTRY}.issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)


if __name__ == "__main__":
    unittest.main(verbosity=2)
