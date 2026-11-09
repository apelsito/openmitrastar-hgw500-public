#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f163_emac_rxrestart16_from_f162 as f163  # noqa: E402


class F163EmacRestart16Tests(unittest.TestCase):
    def test_fixed_size_kernel_only_patch(self) -> None:
        raw = (f163.SRC_BUILD / f"{f163.SRC_BASE}.decompressed.bin").read_bytes()
        patched, report = f163.patch_one(raw, "raw")
        start, _entries, _remainder = f71.parse_first_cpio(raw)
        new_start, _new_entries, _new_remainder = f71.parse_first_cpio(patched)
        self.assertEqual(start, new_start)
        self.assertEqual(len(raw), len(patched))
        self.assertEqual(0, patched.count(f163.OLD_CONTEXT))
        self.assertEqual(1, patched.count(f163.NEW_CONTEXT))
        self.assertEqual(16, report["new_same_cur_rx_pokes"])

    def test_rootfs_cpio_is_unchanged(self) -> None:
        raw = (f163.SRC_BUILD / f"{f163.SRC_BASE}.decompressed.bin").read_bytes()
        patched, _ = f163.patch_one(raw, "raw")
        start, _entries, remainder = f71.parse_first_cpio(raw)
        end = len(raw) - len(remainder)
        self.assertEqual(raw[start:end], patched[start:end])


if __name__ == "__main__":
    unittest.main(verbosity=2)
