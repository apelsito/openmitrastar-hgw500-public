#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f138_5g_hostapd_isolated_raw_from_f137 as f138  # noqa: E402
import build_f139_5g_txpower_limit_from_f138 as f139  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F139TxPowerLimitBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f138.OUT / f"{f138.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f139.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_patch_scope_is_wlan_start_contract_hashes_and_padding(self) -> None:
        allowed = {
            f139.WLAN_ENTRY, f139.START_ENTRY, f139.DRIVER_CONTRACT_ENTRY,
            f139.HASHES_ENTRY, f139.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue({f139.WLAN_ENTRY, f139.START_ENTRY, f139.DRIVER_CONTRACT_ENTRY,
                         f139.HASHES_ENTRY}.issubset(changed))
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_wlan_and_start_script_contain_txpower_fix(self) -> None:
        wlan = self.new_map[f139.WLAN_ENTRY]
        start = self.new_map[f139.START_ENTRY].decode("ascii")
        self.assertEqual(f139.NEW_WLAN_SHA, sha256(wlan))
        self.assertIn(b"OMQTNTXPWR stage=default-limit", wlan)
        self.assertIn("iwconfig-qtn wifi0 txpower 21", start)
        self.assertIn("OMRADIO5_TXPOWER_LIMIT dbm=21", start)

    def test_driver_contract_and_hash_manifest_track_wlan(self) -> None:
        contract = self.new_map[f139.DRIVER_CONTRACT_ENTRY].decode("ascii")
        hashes = self.new_map[f139.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"WLAN_SHA256={f139.NEW_WLAN_SHA}", contract)
        self.assertIn(f"{f139.NEW_WLAN_SHA}  /{f139.WLAN_ENTRY}", hashes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
