from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f121_5g_carrier_probe_from_f120 as f121
import build_f122_5g_beacon_lifetime_from_f121 as f122


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F122BeaconLifetimeBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f122.OUT / f"{f122.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f122.SRC_BUILD / f"{f122.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f122.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f122.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_beacon_lifetime_modules_and_feature_are_active(self) -> None:
        self.assertEqual(sha(self.entries[f122.QDRV_ENTRY]), f122.NEW_QDRV_SHA)
        self.assertEqual(sha(self.entries[f122.WLAN_ENTRY]), f122.NEW_WLAN_SHA)
        self.assertEqual(
            self.entries[f122.FEATURE_ENTRY],
            b"Q3_RADIO5_BEACON_LIFETIME=1\n",
        )

    def test_start_script_preserves_f121_carrier_probe_and_uses_f46_profile(self) -> None:
        script = self.entries[f122.START_ENTRY].decode("ascii")
        self.assertIn("OMRADIO5_CARRIER_PENDING", script)
        self.assertIn("OMRADIO5_VISIBILITY_PROBE", script)
        self.assertIn(f122.NEW_PROFILE, script)
        self.assertIn(f122.NEW_QDRV_SHA, script)
        self.assertNotIn(f122.OLD_PROFILE, script)
        self.assertNotIn(f122.OLD_QDRV_SHA, script)
        self.assertIn("openmitrastar_beacon_v89_wire_enable=1", script)

    def test_driver_contract_and_artifact_hashes_track_replacements(self) -> None:
        contract = self.entries[f122.DRIVER_CONTRACT_ENTRY].decode("ascii")
        hashes = self.entries[f122.HASHES_ENTRY].decode("ascii")
        expected = {
            f122.QDRV_ENTRY: f122.NEW_QDRV_SHA,
            f122.WLAN_ENTRY: f122.NEW_WLAN_SHA,
            f122.FEATURE_ENTRY: sha(self.entries[f122.FEATURE_ENTRY]),
            f122.START_ENTRY: sha(self.entries[f122.START_ENTRY]),
            f122.DRIVER_CONTRACT_ENTRY: sha(self.entries[f122.DRIVER_CONTRACT_ENTRY]),
        }
        self.assertIn(f"QDRV_SHA256={f122.NEW_QDRV_SHA}", contract)
        self.assertIn(f"WLAN_SHA256={f122.NEW_WLAN_SHA}", contract)
        for entry, digest in expected.items():
            self.assertIn(f"{digest}  /{entry}", hashes)

    def test_only_expected_entries_changed_from_f121(self) -> None:
        allowed = {
            f122.QDRV_ENTRY,
            f122.WLAN_ENTRY,
            f122.FEATURE_ENTRY,
            f122.START_ENTRY,
            f122.DRIVER_CONTRACT_ENTRY,
            f122.HASHES_ENTRY,
            f122.PAD_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)


if __name__ == "__main__":
    unittest.main()
