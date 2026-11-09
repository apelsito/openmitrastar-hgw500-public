from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f123_5g_vap_create_observe_from_f122 as f123
import build_f124_5g_vap_before_rf_from_f123 as f124


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F124VapBeforeRfBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f124.OUT / f"{f124.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f124.SRC_BUILD / f"{f124.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f124.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f124.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_vap_create_happens_before_rf_open(self) -> None:
        script = self.entries[f124.START_ENTRY].decode("ascii")
        self.assertIn("OMRADIO5_VAP_CREATE_REPLY", script)
        self.assertIn('[ "$(cat "$rf")" = 0 ] || refuse rf-not-blocked-before-vap', script)
        self.assertIn("control_set_vap_create \"$mac\"", script)
        self.assertIn('refuse rf-open-after-vap', script)
        self.assertLess(
            script.index("control_set_vap_create \"$mac\""),
            script.index("refuse rf-open-after-vap"),
        )
        self.assertNotIn("rf-open-before-vap", script)
        self.assertNotIn("rf-readback-before-vap", script)

    def test_modules_unchanged_from_f123(self) -> None:
        self.assertEqual(sha(self.entries[f122.QDRV_ENTRY]), f122.NEW_QDRV_SHA)
        self.assertEqual(sha(self.entries[f122.WLAN_ENTRY]), f122.NEW_WLAN_SHA)
        self.assertEqual(self.entries[f122.QDRV_ENTRY], self.source_entries[f122.QDRV_ENTRY])
        self.assertEqual(self.entries[f122.WLAN_ENTRY], self.source_entries[f122.WLAN_ENTRY])

    def test_only_expected_entries_changed_from_f123(self) -> None:
        allowed = {
            f124.START_ENTRY,
            f124.HASHES_ENTRY,
            f124.PAD_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)


if __name__ == "__main__":
    unittest.main()
