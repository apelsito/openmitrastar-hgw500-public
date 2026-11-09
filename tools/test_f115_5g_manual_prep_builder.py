from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import build_f115_5g_manual_prep_oemboard_from_f114 as f115
import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F115Manual5gPrepBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (
            f115.OUT
            / f"{f115.BASE_OUT}.decompressed.bin"
        ).read_bytes()
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.manifest = json.loads((f115.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f115.OUT / "build-result.json").read_text(encoding="ascii"))

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_2g_scope_is_preserved_from_f114(self) -> None:
        protected = (
            "usr/sbin/om-radio-modules",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        )
        source_raw = f115.SRC_BUILD / f"{f115.SRC_BASE}.decompressed.bin"
        _start, source_entries, _remainder = f71.parse_first_cpio(source_raw.read_bytes())
        source = {entry.name: entry.data for entry in source_entries}
        for entry in protected:
            self.assertEqual(sha(self.entries[entry]), sha(source[entry]), entry)

    def test_manual_start_rehydrates_runtime_before_calibration_gate(self) -> None:
        start = self.entries[f115.START_ENTRY].decode("ascii")
        self.assertIn("prepare_runtime_sources()", start)
        self.assertLess(
            start.index("prepare_runtime_sources\ncalibration_gate"),
            start.index("refuse origin-not-ready"),
        )
        for token in (
            "/usr/sbin/om-origin-import",
            "/usr/sbin/om-qtn-mac-prepare",
            "/usr/sbin/om-qtn-cal-readonly",
        ):
            self.assertIn(token, start)

    def test_current_rc1_uses_oem_board_radio_values(self) -> None:
        start = self.entries[f115.START_ENTRY].decode("ascii")
        self.assertIn("board_radio_oem_profile=1", start)
        self.assertIn("wifi_hw=7 rfic=4 calstate=3", start)
        self.assertIn("ext_lna_gain=12 ext_lna_bypass_gain=-5", start)
        self.assertIn("tx_power_cal=0 min_tx_power=7 max_tx_power=21", start)

    def test_radio5_artifact_manifest_matches_patched_start(self) -> None:
        start_hash = sha(self.entries[f115.START_ENTRY])
        hashes = self.entries[f115.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"{start_hash}  /usr/sbin/om-radio5-start", hashes)
        self.assertNotIn("45d4511d6dbf20eb5faf8826ff8bf606e5ce9c109dfb3d7b23dfee2f26ac0f00  /usr/sbin/om-radio5-start", hashes)


if __name__ == "__main__":
    unittest.main()
