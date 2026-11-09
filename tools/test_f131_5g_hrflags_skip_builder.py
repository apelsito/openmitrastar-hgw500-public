from __future__ import annotations

import hashlib
import json
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f129_5g_oem_region_txpower_from_f128 as f129
import build_f131_5g_hrflags_skip_from_f129 as f131


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F131HrflagsSkipBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f131.OUT / f"{f131.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f131.SRC_BUILD / f"{f131.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f131.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f131.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_source_documents_the_hrflags_skip_marker(self) -> None:
        source = (
            f131.ROOT
            / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_wlan.c"
        ).read_text(encoding="ascii")
        self.assertIn("OMQDRVHR stage=skip reason=hgw-v89-txpower-discriminant", source)
        self.assertIn("qdrv_hostlink_set_hrflags(qw, 1)", source)

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_qdrv_binary_patch_is_in_place(self) -> None:
        qdrv = self.entries[f131.QDRV_ENTRY]
        source_qdrv = self.source_entries[f131.QDRV_ENTRY]
        self.assertEqual(len(qdrv), len(source_qdrv))
        self.assertEqual(sha(source_qdrv), f122.NEW_QDRV_SHA)
        self.assertNotEqual(sha(qdrv), f122.NEW_QDRV_SHA)
        self.assertEqual(
            qdrv[
                f131.QDRV_BRANCH_FILE_OFF : f131.QDRV_BRANCH_FILE_OFF
                + len(f131.NEW_BRANCH_TO_EPILOGUE)
            ],
            f131.NEW_BRANCH_TO_EPILOGUE,
        )
        self.assertEqual(
            source_qdrv[
                f131.QDRV_BRANCH_FILE_OFF : f131.QDRV_BRANCH_FILE_OFF
                + len(f131.OLD_CALL_PROLOGUE)
            ],
            f131.OLD_CALL_PROLOGUE,
        )
        self.assertIn(b"OMQDRVHR stage=skip reason=hgw-v89\n", qdrv)
        self.assertNotIn(b"OMQDRVHR stage=send vap_present=1 flags=1\n", qdrv)

    def test_integrity_references_follow_new_qdrv_hash(self) -> None:
        qdrv_hash = sha(self.entries[f131.QDRV_ENTRY])
        script = self.entries[f131.START_ENTRY].decode("ascii")
        contract = self.entries[f131.DRIVER_CONTRACT_ENTRY].decode("ascii")
        hashes = self.entries[f131.HASHES_ENTRY].decode("ascii")
        self.assertIn(qdrv_hash, script)
        self.assertIn(f"QDRV_SHA256={qdrv_hash}", contract)
        self.assertIn(f"{qdrv_hash}  /{f131.QDRV_ENTRY}", hashes)
        self.assertNotIn(f122.NEW_QDRV_SHA, script)
        self.assertNotIn(f"QDRV_SHA256={f122.NEW_QDRV_SHA}", contract)

    def test_only_expected_entries_changed_from_f129(self) -> None:
        allowed = {
            f131.QDRV_ENTRY,
            f131.START_ENTRY,
            f131.DRIVER_CONTRACT_ENTRY,
            f131.HASHES_ENTRY,
        }
        changed = {
            name
            for name, data in self.entries.items()
            if name in self.source_entries and sha(data) != sha(self.source_entries[name])
        }
        self.assertEqual(changed, allowed)

    def test_manifest_documents_scope(self) -> None:
        scope = self.manifest["change_scope"]
        self.assertEqual(scope["radio2g"], "unchanged from F129")
        self.assertEqual(scope["wlan"], "unchanged from F129")
        self.assertEqual(scope["queues_dma_rates_rings_forwarding_auc_tx"], "unchanged from F129")
        self.assertEqual(self.manifest["runtime_policy"]["hrflags_set"], "skipped-on-hgw-v89")
        self.assertFalse(self.manifest["runtime_policy"]["rf_before_vap"])


if __name__ == "__main__":
    unittest.main()
