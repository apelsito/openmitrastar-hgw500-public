from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f126_5g_assoc_observe_from_f125 as f126
import build_f127_5g_persistent_ap_from_f126 as f127


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F127PersistentApBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f127.OUT / f"{f127.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f127.SRC_BUILD / f"{f127.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f127.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f127.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_5g_ap_is_persistent_after_ready(self) -> None:
        script = self.entries[f127.START_ENTRY].decode("ascii")
        final = script[script.index('case "$qdrv_profile" in') :]
        final = final[: final.index("printf 'ready\\n'")]
        self.assertIn("product-v6|beacon-lifetime-37527d16", final)
        self.assertIn("association_policy=continuous-ap-observe", final)
        self.assertNotIn("start_assoc_window_guard", final)
        self.assertNotIn("assoc-window-timeout", final)

    def test_preserves_f126_qdrv_wlan_and_vap_before_rf(self) -> None:
        script = self.entries[f127.START_ENTRY].decode("ascii")
        self.assertIn('[ "$(cat "$rf")" = 0 ] || refuse rf-not-blocked-before-vap', script)
        self.assertIn("control_set_vap_create \"$mac\"", script)
        self.assertIn("refuse rf-open-after-vap", script)
        self.assertEqual(sha(self.entries[f122.QDRV_ENTRY]), f122.NEW_QDRV_SHA)
        self.assertEqual(sha(self.entries[f122.WLAN_ENTRY]), f122.NEW_WLAN_SHA)
        self.assertEqual(self.entries[f122.QDRV_ENTRY], self.source_entries[f122.QDRV_ENTRY])
        self.assertEqual(self.entries[f122.WLAN_ENTRY], self.source_entries[f122.WLAN_ENTRY])

    def test_only_start_hashes_and_padding_changed_from_f126(self) -> None:
        allowed = {
            f127.START_ENTRY,
            f127.HASHES_ENTRY,
            f127.PAD_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_manifest_documents_no_driver_or_datapath_change(self) -> None:
        scope = self.manifest["change_scope"]
        self.assertEqual(scope["qdrv"], "unchanged from F126")
        self.assertEqual(scope["wlan"], "unchanged from F126")
        self.assertEqual(scope["radio2g"], "unchanged from F126")
        self.assertEqual(scope["queues_dma_rates_rings_forwarding_auc_tx"], "unchanged from F126")
        self.assertFalse(self.manifest["runtime_policy"]["association_window_auto_stop"])


if __name__ == "__main__":
    unittest.main()
