#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f137_5g_post_hostapd_rearm_from_f136 as f137  # noqa: E402
import build_f138_5g_hostapd_isolated_raw_from_f137 as f138  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F138HostapdIsolatedRawBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f137.OUT / f"{f137.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f138.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_replaces_only_hostapd_hashes_and_padding(self) -> None:
        allowed = {f138.HOSTAPD_ENTRY, f138.HASHES_ENTRY, f138.PAD_ENTRY}
        changed = {
            name for name in self.old_map
            if self.old_map[name] != self.new_map[name]
        }
        self.assertEqual(allowed, changed)
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)

    def test_embeds_isolated_raw_socket_fix(self) -> None:
        hostapd = self.new_map[f138.HOSTAPD_ENTRY]
        self.assertEqual(f138.NEW_HOSTAPD_SHA, sha256(hostapd))
        self.assertIn(f138.HOSTAPD_MARKER, hostapd)
        self.assertEqual(f138.OLD_HOSTAPD_SHA, sha256(self.old_map[f138.HOSTAPD_ENTRY]))

    def test_artifact_hash_manifest_tracks_new_hostapd(self) -> None:
        hashes = self.new_map[f138.HASHES_ENTRY].decode("ascii")
        self.assertIn(
            f"{f138.NEW_HOSTAPD_SHA}  /{f138.HOSTAPD_ENTRY}",
            hashes,
        )
        self.assertNotIn(
            f"{f138.OLD_HOSTAPD_SHA}  /{f138.HOSTAPD_ENTRY}",
            hashes,
        )
        self.assertEqual(f138.HOSTAPD_ENTRY, self.report["hostapd"]["entry"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
