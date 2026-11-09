from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f129_5g_oem_region_txpower_from_f128 as f129
import build_f130_5g_rf_before_vap_from_f129 as f130


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F130RfBeforeVapBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f130.OUT / f"{f130.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f130.SRC_BUILD / f"{f130.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f130.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f130.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_start_script_opens_rf_before_vap_creation(self) -> None:
        script = self.entries[f130.START_ENTRY].decode("ascii")
        rf_log = script.index("OMRADIO5_RF_BEFORE_VAP")
        vap_create = script.index('control_set_vap_create "$mac"')
        self.assertLess(rf_log, vap_create)
        self.assertIn("rf-open-before-vap", script)
        self.assertIn("rf-readback-before-vap", script)
        self.assertIn("vap-marker-rf-open", script)
        self.assertNotIn("rf-open-after-vap", script)
        self.assertNotIn("rf-readback-after-vap", script)
        self.assertIn("rf_before_vap=1", script)

    def test_preserves_f129_drivers_and_datapath(self) -> None:
        self.assertEqual(sha(self.entries[f122.QDRV_ENTRY]), f122.NEW_QDRV_SHA)
        self.assertEqual(sha(self.entries[f122.WLAN_ENTRY]), f122.NEW_WLAN_SHA)
        self.assertEqual(self.entries[f122.QDRV_ENTRY], self.source_entries[f122.QDRV_ENTRY])
        self.assertEqual(self.entries[f122.WLAN_ENTRY], self.source_entries[f122.WLAN_ENTRY])

    def test_only_start_hashes_and_padding_changed_from_f129(self) -> None:
        allowed = {
            f130.START_ENTRY,
            f130.HASHES_ENTRY,
            f130.PAD_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_manifest_documents_scope(self) -> None:
        scope = self.manifest["change_scope"]
        self.assertEqual(scope["qdrv"], "unchanged from F129")
        self.assertEqual(scope["wlan"], "unchanged from F129")
        self.assertEqual(scope["radio2g"], "unchanged from F129")
        self.assertEqual(scope["queues_dma_rates_rings_forwarding_auc_tx"], "unchanged from F129")
        self.assertTrue(self.manifest["runtime_policy"]["rf_before_vap"])
        self.assertEqual(self.manifest["runtime_policy"]["txpower_path"], "oem-regional-init-only")


if __name__ == "__main__":
    unittest.main()
