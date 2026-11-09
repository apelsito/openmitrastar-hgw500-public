from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f127_5g_persistent_ap_from_f126 as f127
import build_f128_5g_visibility_power_gate_from_f127 as f128


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F128VisibilityPowerGateBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f128.OUT / f"{f128.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f128.SRC_BUILD / f"{f128.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f128.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f128.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_start_script_seeds_txpower_before_hostapd(self) -> None:
        script = self.entries[f128.START_ENTRY].decode("ascii")
        txpower = script.index("OMRADIO5_TXPOWER_PARITY")
        hostapd = script.index("/usr/sbin/hostapd-qtn")
        self.assertLess(txpower, hostapd)
        self.assertIn("qtn_txpower_val=16717057", script)
        self.assertIn("qtn_reg_txpower_val=65301", script)
        self.assertIn("iwpriv-qtn wifi0 init_txpower", script)
        self.assertIn("iwpriv-qtn wifi0 cfg_txpower", script)
        self.assertIn("iwpriv-qtn wifi0 cfg_reg_txpower", script)
        self.assertIn("iwpriv-qtn wifi0 doth 1", script)
        self.assertIn("iwpriv-qtn wifi0 tpc 1", script)

    def test_ready_is_fail_closed_on_invisible_rf_state(self) -> None:
        script = self.entries[f128.START_ENTRY].decode("ascii")
        ready = script.index("printf 'ready\\n' >\"$state/ready\"")
        post_hostapd = script.index("require_radio5_visibility_state post-hostapd")
        post_coc = script.index("require_radio5_visibility_state post-coc")
        self.assertLess(post_hostapd, ready)
        self.assertLess(post_coc, ready)
        self.assertIn("visibility-txpower-zero-$label", script)
        self.assertIn("Mode: (null)", script)
        self.assertIn("Frequency: -1 MHz", script)
        self.assertIn("OMRADIO5_VISIBILITY_STATE_PASS", script)

    def test_preserves_f127_drivers_and_datapath(self) -> None:
        self.assertEqual(sha(self.entries[f122.QDRV_ENTRY]), f122.NEW_QDRV_SHA)
        self.assertEqual(sha(self.entries[f122.WLAN_ENTRY]), f122.NEW_WLAN_SHA)
        self.assertEqual(self.entries[f122.QDRV_ENTRY], self.source_entries[f122.QDRV_ENTRY])
        self.assertEqual(self.entries[f122.WLAN_ENTRY], self.source_entries[f122.WLAN_ENTRY])

    def test_only_start_hashes_and_padding_changed_from_f127(self) -> None:
        allowed = {
            f128.START_ENTRY,
            f128.HASHES_ENTRY,
            f128.PAD_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_manifest_documents_scope(self) -> None:
        scope = self.manifest["change_scope"]
        self.assertEqual(scope["qdrv"], "unchanged from F127")
        self.assertEqual(scope["wlan"], "unchanged from F127")
        self.assertEqual(scope["radio2g"], "unchanged from F127")
        self.assertEqual(scope["queues_dma_rates_rings_forwarding_auc_tx"], "unchanged from F127")
        self.assertFalse(self.manifest["runtime_policy"]["visibility_false_ready_allowed"])
        self.assertFalse(self.manifest["runtime_policy"]["txpower_zero_ready_allowed"])


if __name__ == "__main__":
    unittest.main()
