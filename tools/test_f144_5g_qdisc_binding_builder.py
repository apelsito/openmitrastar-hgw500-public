#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as f143  # noqa: E402
import build_f144_5g_qdisc_binding_from_f143 as f144  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F144QdiscBindingBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f143.OUT / f"{f143.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f144.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_rebuilt_qdrv_has_qdisc_and_f143_markers(self) -> None:
        old = self.old_map[f143.QDRV_ENTRY]
        new = self.new_map[f143.QDRV_ENTRY]
        self.assertEqual(f144.F143_QDRV_SHA, sha256(old))
        self.assertEqual(f144.NEW_QDRV_SHA, sha256(new))
        self.assertIn(b"OMQDRVSCH stage=bind source=qdisc-sleeping", new)
        self.assertIn(b"OMQDRVHLINK stage=free-deferred", new)
        self.assertIn(b"OMQDRVHR stage=timer-disabled reason=hgw-v89", new)

    def test_only_qdrv_contract_hashes_start_and_padding_change(self) -> None:
        allowed = {
            f143.QDRV_ENTRY, f143.START_ENTRY, f143.DRIVER_CONTRACT_ENTRY,
            f143.HASHES_ENTRY, f143.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue({f143.QDRV_ENTRY, f143.START_ENTRY,
                         f143.DRIVER_CONTRACT_ENTRY, f143.HASHES_ENTRY}.issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(self.old_map[f143.WLAN_ENTRY], self.new_map[f143.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)


if __name__ == "__main__":
    unittest.main(verbosity=2)
