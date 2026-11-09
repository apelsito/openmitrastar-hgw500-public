from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import build_f71_qcsapi_interp_from_f70 as f71
import build_f118_5g_qdrv_rfgate_vap_from_f117 as f118


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F118QdrvRfGateVapBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f118.OUT / f"{f118.BASE_OUT}.decompressed.bin").read_bytes()
        source_raw = f118.SRC_BUILD / f"{f118.SRC_BASE}.decompressed.bin"
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        _source_start, source_entries, _source_remainder = f71.parse_first_cpio(
            source_raw.read_bytes()
        )
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.source_entries = {entry.name: entry.data for entry in source_entries}
        cls.manifest = json.loads((f118.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f118.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_qdrv_is_the_only_driver_payload_changed(self) -> None:
        protected = (
            "usr/sbin/om-radio5-start",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/hbm.ko",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/switch_emac.ko",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/wlan.ko",
        )
        for entry in protected:
            self.assertEqual(sha(self.entries[entry]), sha(self.source_entries[entry]), entry)
        self.assertNotEqual(
            sha(self.entries[f118.QDRV_ENTRY]), sha(self.source_entries[f118.QDRV_ENTRY])
        )

    def test_qdrv_hash_matches_rebuilt_artifact_and_hash_manifest(self) -> None:
        qdrv_hash = sha(self.entries[f118.QDRV_ENTRY])
        self.assertEqual(qdrv_hash, sha(f118.NEW_QDRV.read_bytes()))
        self.assertEqual(qdrv_hash, self.result["qdrv_sha256"])
        self.assertEqual(qdrv_hash, self.manifest["qdrv_source"]["sha256"])
        hashes = self.entries[f118.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"{qdrv_hash}  /{f118.QDRV_ENTRY}", hashes)

    def test_qdrv_source_has_rf_vap_gate_fix(self) -> None:
        source = (f118.ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_control.c").read_text(
            encoding="ascii"
        )
        allow_start = source.index('!strcmp(argv[0], "start") && argc == 5')
        allow_end = source.index("return 0;", allow_start)
        allow_block = source[allow_start:allow_end]
        self.assertIn("openmitrastar_sequential_mac0_valid", allow_block)
        self.assertNotIn("!qdrv_openmitrastar_rf_gate_enabled()", allow_block)


if __name__ == "__main__":
    unittest.main()
