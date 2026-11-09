from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import build_f116_5g_wifi0_up_before_hostapd_from_f115 as f116
import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "arm_f116_5g_wifi0_up_flash.ps1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F116Wifi0UpBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f116.OUT / f"{f116.BASE_OUT}.decompressed.bin").read_bytes()
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.manifest = json.loads((f116.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f116.OUT / "build-result.json").read_text(encoding="ascii"))
        cls.start = cls.entries[f116.START_ENTRY].decode("ascii")

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_2g_scope_is_preserved_from_f115(self) -> None:
        source_raw = f116.SRC_BUILD / f"{f116.SRC_BASE}.decompressed.bin"
        _start, source_entries, _remainder = f71.parse_first_cpio(source_raw.read_bytes())
        source = {entry.name: entry.data for entry in source_entries}
        protected = (
            "usr/sbin/om-radio-modules",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        )
        for entry in protected:
            self.assertEqual(sha(self.entries[entry]), sha(source[entry]), entry)

    def test_wifi0_up_happens_after_rf_and_before_hostapd(self) -> None:
        rf_open = self.start.index("printf '1\\n' >\"$rf\" || refuse rf-open")
        rf_readback = self.start.index('[ "$(cat "$rf")" = 1 ] || refuse rf-readback')
        wifi0_up = self.start.index("ifconfig wifi0 up || refuse wifi0-up")
        wifi0_readback = self.start.index("refuse wifi0-up-readback")
        hostapd = self.start.index('/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &')
        self.assertLess(rf_open, rf_readback)
        self.assertLess(rf_readback, wifi0_up)
        self.assertLess(wifi0_up, wifi0_readback)
        self.assertLess(wifi0_readback, hostapd)

    def test_f115_runtime_prep_and_oem_board_values_are_preserved(self) -> None:
        for token in (
            "prepare_runtime_sources()",
            "/usr/sbin/om-origin-import",
            "/usr/sbin/om-qtn-mac-prepare",
            "/usr/sbin/om-qtn-cal-readonly",
            "board_radio_oem_profile=1",
            "wifi_hw=7 rfic=4 calstate=3",
            "ext_lna_gain=12 ext_lna_bypass_gain=-5",
            "tx_power_cal=0 min_tx_power=7 max_tx_power=21",
        ):
            self.assertIn(token, self.start)

    def test_radio5_artifact_manifest_matches_patched_start(self) -> None:
        start_hash = sha(self.entries[f116.START_ENTRY])
        hashes = self.entries[f116.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"{start_hash}  /usr/sbin/om-radio5-start", hashes)
        self.assertEqual(start_hash, self.manifest["patch"]["start_script"]["new_sha256"])

    def test_flash_wrapper_targets_f116_over_f115(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("OPENMITRASTAR_Q3_F116_5G_WIFI0_UP_BEFORE_HOSTAPD", text)
        self.assertIn(self.result["candidate_sha256"], text)
        self.assertIn(str(self.result["candidate_bytes"]), text)
        self.assertIn(self.result["candidate_crc32"], text)
        self.assertIn(self.result["full_slot_crc32"], text)
        self.assertIn('[string]$CurrentLiveCrc32 = "3b4d748a"', text)
        self.assertIn("-NoRxAbortSeconds", text)


if __name__ == "__main__":
    unittest.main()
