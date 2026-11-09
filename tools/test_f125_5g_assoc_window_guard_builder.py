from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f124_5g_vap_before_rf_from_f123 as f124
import build_f125_5g_assoc_window_guard_from_f124 as f125


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F125AssocWindowGuardBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f125.OUT / f"{f125.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f125.SRC_BUILD / f"{f125.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f125.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f125.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_assoc_window_guard_is_installed_after_ready_gates(self) -> None:
        script = self.entries[f125.START_ENTRY].decode("ascii")
        self.assertIn("start_assoc_window_guard()", script)
        self.assertIn("OMRADIO5_ASSOC_WINDOW event=sta-observed action=stop", script)
        self.assertIn("OMRADIO5_ASSOC_WINDOW event=timeout action=stop", script)
        self.assertIn("assoc-window-sta-observed", script)
        self.assertIn("assoc-window-timeout", script)
        self.assertIn("association_policy=$association_policy", script)
        self.assertLess(script.index("start_assoc_window_guard()"), script.index("start_assoc_window_guard\nfi"))
        self.assertLess(script.index("start_assoc_window_guard\nfi"), script.index("printf 'ready\\n' >\"$state/ready\""))

    def test_preserves_f124_vap_before_rf_ordering(self) -> None:
        script = self.entries[f125.START_ENTRY].decode("ascii")
        self.assertIn('[ "$(cat "$rf")" = 0 ] || refuse rf-not-blocked-before-vap', script)
        self.assertIn("control_set_vap_create \"$mac\"", script)
        self.assertIn('refuse rf-open-after-vap', script)
        self.assertLess(
            script.index("control_set_vap_create \"$mac\""),
            script.index("refuse rf-open-after-vap"),
        )

    def test_modules_unchanged_from_f124(self) -> None:
        self.assertEqual(sha(self.entries[f122.QDRV_ENTRY]), f122.NEW_QDRV_SHA)
        self.assertEqual(sha(self.entries[f122.WLAN_ENTRY]), f122.NEW_WLAN_SHA)
        self.assertEqual(self.entries[f122.QDRV_ENTRY], self.source_entries[f122.QDRV_ENTRY])
        self.assertEqual(self.entries[f122.WLAN_ENTRY], self.source_entries[f122.WLAN_ENTRY])

    def test_only_expected_entries_changed_from_f124(self) -> None:
        allowed = {
            f125.START_ENTRY,
            f125.HASHES_ENTRY,
            f125.PAD_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)


if __name__ == "__main__":
    unittest.main()
