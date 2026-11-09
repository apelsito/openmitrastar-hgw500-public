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
import build_f148_5g_subport_map_pair_from_f147 as f148  # noqa: E402


class F148SubportMapPairBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = f148.SRC_BUILD / f"{f148.SRC_BASE}.decompressed.bin"
        cls.source = source.read_bytes()
        cls.patched, cls.report = f148.patch_cpio(cls.source)
        _, old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in old_entries}
        cls.new_map = {entry.name: entry.data for entry in new_entries}

    def test_replaces_exact_matched_qdrv_wlan_pair(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.old_map[engine.QDRV_ENTRY]).hexdigest(),
            f148.OLD_QDRV_SHA,
        )
        self.assertEqual(
            hashlib.sha256(self.old_map[engine.WLAN_ENTRY]).hexdigest(),
            f148.OLD_WLAN_SHA,
        )
        self.assertEqual(
            hashlib.sha256(self.new_map[engine.QDRV_ENTRY]).hexdigest(),
            f148.NEW_QDRV_SHA,
        )
        self.assertEqual(
            hashlib.sha256(self.new_map[engine.WLAN_ENTRY]).hexdigest(),
            f148.NEW_WLAN_SHA,
        )
        self.assertIn(b"OMQDRVTXPATH stage=auc-submit", self.new_map[engine.QDRV_ENTRY])

    def test_payload_scope_and_fixed_layout(self) -> None:
        allowed = {
            engine.QDRV_ENTRY,
            engine.WLAN_ENTRY,
            engine.START_ENTRY,
            engine.DRIVER_CONTRACT_ENTRY,
            engine.HASHES_ENTRY,
            engine.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_integrity_contract_tracks_both_modules(self) -> None:
        contract = self.new_map[engine.DRIVER_CONTRACT_ENTRY].decode("ascii")
        start = self.new_map[engine.START_ENTRY].decode("ascii")
        hashes = self.new_map[engine.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"QDRV_SHA256={f148.NEW_QDRV_SHA}", contract)
        self.assertIn(f"WLAN_SHA256={f148.NEW_WLAN_SHA}", contract)
        self.assertIn(f148.NEW_QDRV_SHA, start)
        self.assertIn(f148.NEW_QDRV_SHA, hashes)
        self.assertIn(f148.NEW_WLAN_SHA, hashes)

    def test_source_defines_mapped_subport_contract(self) -> None:
        compat = (
            ROOT
            / "work/linux510-radio-port/quantenna/qdrv/compat/include/openmitrastar_qdrv_compat.h"
        ).read_text(encoding="ascii")
        self.assertIn("#define BR_SUBPORT_MAP(port) ((port) | 0x8000U)", compat)
        self.assertIn("#define BR_SUBPORT_UNMAP(port) ((port) & 0x7fffU)", compat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
