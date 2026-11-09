#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "tools/qtn_w3_native_madwifi_ap.sh"
ROLLBACK = ROOT / "tools/qtn_w3_native_ap_rollback.sh"


class NativeMadwifiApTests(unittest.TestCase):
    def test_fixed_es_channel36_bw80(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("region=ES channel=36 bw=80", text)
        self.assertIn("get_region", text)
        self.assertIn("21317", text)
        self.assertIn("Frequency:5.18 GHz", text)
        self.assertIn("11ac80", text)

    def test_wpa2_ccmp_and_external_psk(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("wpa=2", text)
        self.assertIn("wpa_pairwise=CCMP", text)
        self.assertNotIn("ieee80211w", text)
        self.assertIn("psk=redacted", text)
        self.assertNotIn("qtn01234", text)
        self.assertIn("wlan_ccmp", text)
        self.assertIn("wlan_xauth", text)
        self.assertIn("338beaae1e3f3bc951b16d4bea1871d42d184170fc95f5efd200aa46e45dc269", text)

    def test_rf_opens_once_after_rollback_arm(self):
        text = START.read_text(encoding="utf-8")
        self.assertLess(text.index("rollback-armed"), text.index("printf '1"))
        self.assertEqual(text.count("printf '1\\n' >\"$rf\""), 1)

    def test_local_rollback_closes_rf_and_detaches_wifi(self):
        text = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("ifconfig wifi0 down", text)
        self.assertIn("brctl delif br0 wifi0", text)
        self.assertIn("printf '0", text)
        self.assertIn('"$root/hostapd.conf"', text)

    def test_no_flash_surface(self):
        text = (START.read_text(encoding="utf-8") + ROLLBACK.read_text(encoding="utf-8")).lower()
        for forbidden in ("flash_erase", "mtd write", "saveenv", "nandwrite"):
            self.assertNotIn(forbidden, text)

    def test_bounded_debug_goes_to_file(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn('"$hostapd" -B -dd -P', text)
        self.assertIn('logger_stdout_level=0', text)

    def test_quantenna_cli_gate_uses_ping_and_config(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn(' ping >"$root/ping"', text)
        self.assertIn(' get_config >"$root/get_config"', text)
        self.assertIn('grep -qx PONG', text)
        self.assertIn('wifi0: Setup of interface done.', text)
        self.assertNotIn(' ping -c ', text)
        self.assertNotIn('hostapd_state)=ENABLED', text)


if __name__ == "__main__":
    unittest.main()
