from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import build_f117_5g_rf_before_vap_from_f116 as f117
import build_f71_qcsapi_interp_from_f70 as f71


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class F117RfBeforeVapBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f117.OUT / f"{f117.BASE_OUT}.decompressed.bin").read_bytes()
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        cls.entries = {entry.name: entry.data for entry in entries}
        cls.manifest = json.loads((f117.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((f117.OUT / "build-result.json").read_text(encoding="ascii"))
        cls.start = cls.entries[f117.START_ENTRY].decode("ascii")

    def test_builder_produced_flashable_fixed_size_candidate(self) -> None:
        self.assertEqual(self.result["status"], "PASS")
        self.assertEqual(self.manifest["bootbase_contract"]["result"], "PASS")
        self.assertEqual(self.manifest["persistent_entry_contract"]["result"], "PASS")
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["raw_bytes_preserved"])
        self.assertTrue(self.manifest["patch"]["fixed_size_compensation"]["cpio_end_preserved"])

    def test_2g_scope_is_preserved_from_f116(self) -> None:
        source_raw = f117.SRC_BUILD / f"{f117.SRC_BASE}.decompressed.bin"
        _start, source_entries, _remainder = f71.parse_first_cpio(source_raw.read_bytes())
        source = {entry.name: entry.data for entry in source_entries}
        protected = (
            "usr/sbin/om-radio-modules",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
            "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        )
        for entry in protected:
            self.assertEqual(sha(self.entries[entry]), sha(source[entry]), entry)

    def test_rf_opens_before_vap_create_and_stays_open_for_config(self) -> None:
        fatal_gate = self.start.index('refuse fatal-before-vap')
        rf_open = self.start.index("printf '1\\n' >\"$rf\" || refuse rf-open-before-vap")
        rf_readback = self.start.index("refuse rf-readback-before-vap")
        vap_gate = self.start.index("openmitrastar_single_vap_create", rf_readback)
        vap_create = self.start.index('control_set "start 0 ap wifi0 $mac"')
        before_config = self.start.index("refuse rf-not-open-before-config")
        during_config = self.start.index("refuse rf-not-open-during-config")
        self.assertLess(fatal_gate, rf_open)
        self.assertLess(rf_open, rf_readback)
        self.assertLess(rf_readback, vap_gate)
        self.assertLess(vap_gate, vap_create)
        self.assertLess(vap_create, before_config)
        self.assertLess(before_config, during_config)

    def test_wifi0_up_still_happens_before_hostapd(self) -> None:
        wifi0_up = self.start.index("ifconfig wifi0 up || refuse wifi0-up")
        hostapd = self.start.index('/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &')
        self.assertLess(wifi0_up, hostapd)
        self.assertIn("OMRADIO5_AUC_TX_MODE mode=auc value=1 rf=open reversible=1", self.start)

    def test_radio5_artifact_manifest_matches_patched_start(self) -> None:
        start_hash = sha(self.entries[f117.START_ENTRY])
        hashes = self.entries[f117.HASHES_ENTRY].decode("ascii")
        self.assertIn(f"{start_hash}  /usr/sbin/om-radio5-start", hashes)
        self.assertEqual(start_hash, self.manifest["patch"]["start_script"]["new_sha256"])


if __name__ == "__main__":
    unittest.main()
