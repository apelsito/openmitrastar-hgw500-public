#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f157_5g_persistent_bridge_from_f156 as f157  # noqa: E402


class F157PersistentBridgeBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f157.SRC_BUILD / f"{f157.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f157.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_replaces_only_start_and_integrity_metadata(self) -> None:
        allowed = {engine.START_ENTRY, engine.HASHES_ENTRY, engine.PAD_ENTRY}
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(self.old_map[engine.QDRV_ENTRY], self.new_map[engine.QDRV_ENTRY])
        self.assertEqual(self.old_map[engine.WLAN_ENTRY], self.new_map[engine.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_start_uses_oem_like_bridge_topology(self) -> None:
        start = self.new_map[engine.START_ENTRY]
        self.assertEqual(start.count(b"'bridge=br0'"), 2)
        self.assertIn(b"brctl addif br0 wifi0", start)
        self.assertIn(b"OMQTN5G_BRIDGE_READY", start)
        self.assertIn(b"br0_members=eth0,wlan0,wifi0", start)
        self.assertNotIn(b"ifconfig wifi0 192.168.77.1", start)
        self.assertIn(b"OMRADIO5_TXBA_POLICY disabled=1 source=f156", start)


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
