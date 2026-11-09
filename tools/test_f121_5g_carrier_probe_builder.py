from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f120_5g_power_selection_from_f119 as f120
import build_f121_5g_carrier_probe_from_f120 as f121


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F121CarrierProbeBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f121.OUT / f"{f121.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f121.SRC_BUILD / f"{f121.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f121.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f121.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_carrier_probe_keeps_hostapd_alive_for_visibility_test(self) -> None:
        script = self.entries[f121.START_ENTRY].decode("ascii")
        self.assertIn("OMRADIO5_CARRIER_PENDING", script)
        self.assertIn("OMRADIO5_VISIBILITY_PROBE", script)
        self.assertIn("led_gate=carrier-pending-skip", script)
        self.assertLess(
            script.index("/usr/sbin/iwpriv-qtn wifi0 pm 0"),
            script.index("product_v6_carrier_gate=0"),
        )
        self.assertNotIn("refuse coc-carrier-not-ready\n", script)

    def test_only_start_hashes_and_padding_changed_from_f120(self) -> None:
        allowed = {f120.START_ENTRY, f120.HASHES_ENTRY, f120.PAD_ENTRY}
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_hash_manifest_tracks_new_start_script(self) -> None:
        hashes = self.entries[f121.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"{sha(self.entries[f121.START_ENTRY])}  /{f121.START_ENTRY}", hashes)
        self.assertEqual(
            self.manifest["patch"]["artifact_hashes"]["new_start_sha256"],
            sha(self.entries[f121.START_ENTRY]),
        )


if __name__ == "__main__":
    unittest.main()
