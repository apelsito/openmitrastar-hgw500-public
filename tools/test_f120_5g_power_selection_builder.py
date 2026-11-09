from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f119_5g_qdrv_contract_from_f118 as f119
import build_f120_5g_power_selection_from_f119 as f120


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F120PowerSelectionBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f120.OUT / f"{f120.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f120.SRC_BUILD / f"{f120.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f120.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f120.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_start_script_sets_power_selection_before_clearsram(self) -> None:
        script = self.entries[f120.START_ENTRY].decode("ascii")
        self.assertIn("control_set 'set power_selection 2' power-selection", script)
        self.assertLess(
            script.index("control_set 'set lock_checksum_list 1' checksum-lock"),
            script.index("control_set 'set power_selection 2' power-selection"),
        )
        self.assertLess(
            script.index("control_set 'set power_selection 2' power-selection"),
            script.index("control_set clearsram clearsram"),
        )
        self.assertIn("OMQDRVSEQ stage=start-pass mask=0xff rf=blocked vap=blocked", script)

    def test_only_start_hashes_and_padding_changed_from_f119(self) -> None:
        allowed = {f119.START_ENTRY, f119.HASHES_ENTRY, f119.PAD_ENTRY}
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_hash_manifest_tracks_new_start_script(self) -> None:
        hashes = self.entries[f120.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"{sha(self.entries[f120.START_ENTRY])}  /{f120.START_ENTRY}", hashes)
        self.assertEqual(
            self.manifest["patch"]["artifact_hashes"]["new_start_sha256"],
            sha(self.entries[f120.START_ENTRY]),
        )


if __name__ == "__main__":
    unittest.main()
