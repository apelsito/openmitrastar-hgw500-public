#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "tools/qtn_w3_native_madwifi_open_ap.sh"
RUNNER = ROOT / "tools/run_qtn_w3_native_open_ap.py"
ROLLBACK = ROOT / "tools/qtn_w3_native_ap_rollback.sh"


class NativeOpenApTests(unittest.TestCase):
    def test_fixed_es_channel36_bw80(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("region=ES channel=36 bw=80 security=OPEN", text)
        self.assertIn("get_region", text)
        self.assertIn("21317", text)
        self.assertIn("Frequency:5.18 GHz", text)
        self.assertIn("11ac80", text)

    def test_is_unambiguously_open(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("wpa=0", text)
        self.assertNotIn("wpa_passphrase", text)
        self.assertNotIn("WPA-PSK", text)
        self.assertNotIn("wpa_pairwise", text)
        self.assertIn("hostapd_not_open", text)

    def test_rf_opens_once_after_rollback_arm(self):
        text = START.read_text(encoding="utf-8")
        self.assertLess(text.index("rollback-armed"), text.index("printf '1"))
        self.assertEqual(text.count("printf '1\\n' >\"$rf\""), 1)

    def test_local_rollback_closes_rf_and_detaches_wifi(self):
        text = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("ifconfig wifi0 down", text)
        self.assertIn("brctl delif br0 wifi0", text)
        self.assertIn("printf '0", text)

    def test_no_flash_or_secret_surface(self):
        text = (START.read_text(encoding="utf-8") + RUNNER.read_text(encoding="utf-8")).lower()
        for forbidden in ("flash_erase", "mtd write", "saveenv", "nandwrite", "psk-file"):
            self.assertNotIn(forbidden, text)

    def test_runner_has_exact_pass_markers(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("W3_QTN_NATIVE_OPEN_AP_DRY_RUN_PASS=1", text)
        self.assertIn("W3_QTN_NATIVE_OPEN_AP_EXPERIMENT_PASS=1", text)
        self.assertIn("W3_QTN_NATIVE_OPEN_AP_PASS=1", text)


if __name__ == "__main__":
    unittest.main()
