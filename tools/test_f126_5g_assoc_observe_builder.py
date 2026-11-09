from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f125_5g_assoc_window_guard_from_f124 as f125
import build_f126_5g_assoc_observe_from_f125 as f126


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F126AssocObserveBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f126.OUT / f"{f126.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f126.SRC_BUILD / f"{f126.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f126.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f126.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_assoc_window_covers_beacon_lifetime_profile(self) -> None:
        script = self.entries[f126.START_ENTRY].decode("ascii")
        self.assertIn("capture_assoc_window_snapshot()", script)
        self.assertIn("product-v6|beacon-lifetime-37527d16", script)
        self.assertIn("association_policy=first-sta-stop-20s", script)
        self.assertIn("OMQDRVASSOC|OMQDRVRXMGMT|OMQDRVTXPATH", script)
        self.assertIn("assoc-window-sta-observed", script)
        self.assertIn("assoc-window-timeout", script)
        self.assertIn("assoc-window-hostapd-dead", script)

    def test_preserves_f125_qdrv_wlan_and_vap_before_rf(self) -> None:
        script = self.entries[f126.START_ENTRY].decode("ascii")
        self.assertIn('[ "$(cat "$rf")" = 0 ] || refuse rf-not-blocked-before-vap', script)
        self.assertIn("control_set_vap_create \"$mac\"", script)
        self.assertIn("refuse rf-open-after-vap", script)
        self.assertEqual(sha(self.entries[f122.QDRV_ENTRY]), f122.NEW_QDRV_SHA)
        self.assertEqual(sha(self.entries[f122.WLAN_ENTRY]), f122.NEW_WLAN_SHA)
        self.assertEqual(self.entries[f122.QDRV_ENTRY], self.source_entries[f122.QDRV_ENTRY])
        self.assertEqual(self.entries[f122.WLAN_ENTRY], self.source_entries[f122.WLAN_ENTRY])

    def test_only_script_hashes_and_padding_changed_from_f125(self) -> None:
        allowed = {
            f126.START_ENTRY,
            f126.HASHES_ENTRY,
            f126.PAD_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_does_not_import_or_embed_v62_scheduler_contract(self) -> None:
        builder = (f126.ROOT / "tools/build_f126_5g_assoc_observe_from_f125.py").read_text(encoding="utf-8")
        script = self.entries[f126.START_ENTRY].decode("ascii")
        self.assertNotIn("v62", builder.lower())
        self.assertNotIn("5b9ae80e", builder)
        self.assertNotIn("qdrv-v6.2", script)
        self.assertEqual(self.result["qdrv_sha256"], f125.f122.NEW_QDRV_SHA)


if __name__ == "__main__":
    unittest.main()
