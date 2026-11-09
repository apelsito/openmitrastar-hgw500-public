from __future__ import annotations

import hashlib
import json
import re
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f119_5g_qdrv_contract_from_f118 as f119


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F119QdrvContractBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f119.OUT / f"{f119.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f119.SRC_BUILD / f"{f119.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f119.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f119.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_driver_contract_matches_embedded_qdrv(self) -> None:
        qdrv_hash = sha(self.entries[f119.QDRV_ENTRY])
        contract = self.entries[f119.DRIVER_CONTRACT_ENTRY].decode("ascii")
        self.assertIn(f"QDRV_SHA256={qdrv_hash}", contract)
        hashes = self.entries[f119.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"{sha(self.entries[f119.DRIVER_CONTRACT_ENTRY])}  /{f119.DRIVER_CONTRACT_ENTRY}", hashes)
        self.assertIn(f"{qdrv_hash}  /{f119.QDRV_ENTRY}", hashes)

    def test_only_contract_changed_from_f118(self) -> None:
        allowed = {f119.DRIVER_CONTRACT_ENTRY, f119.HASHES_ENTRY, f119.PAD_ENTRY}
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_contract_old_hash_was_replaced(self) -> None:
        patch = self.manifest["patch"]["driver_contract"]
        self.assertRegex(patch["old_qdrv_line"], r"^QDRV_SHA256=[0-9a-f]{64}$")
        self.assertEqual(patch["new_qdrv_sha256"], self.result["qdrv_sha256"])
        self.assertNotEqual(
            re.sub(r"^QDRV_SHA256=", "", patch["old_qdrv_line"]),
            patch["new_qdrv_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
