#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class F151BridgeTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (ROOT / "tools/q3_f151_bridge_trial_remote.sh").read_text(encoding="utf-8")

    def test_trial_has_local_rollback_before_bridge_mutation(self) -> None:
        self.assertLess(self.text.index("sleep 420"), self.text.index("brctl addif br0 wifi0"))
        self.assertIn("brctl delif br0 wifi0", self.text)
        self.assertIn("ifconfig wifi0 192.168.77.1", self.text)
        self.assertNotIn("/usr/sbin/om-radio5-stop bridge-trial-rollback", self.text)
        self.assertIn("bridge-member-missing-after-addif", self.text)
        self.assertIn("bridge-member-missing-after-hostapd", self.text)
        self.assertIn("ifconfig wifi0 0.0.0.0 up", self.text)
        self.assertIn("wifi0-ip-still-present", self.text)

    def test_trial_preserves_management_and_wpa2_contracts(self) -> None:
        rollback, apply = self.text.split('case "$action" in', 1)
        self.assertIn("/sys/class/net/br0/brif/eth0", self.text)
        self.assertIn("/sys/class/net/br0/brif/wlan0", self.text)
        self.assertIn("ifconfig br0 2>/dev/null | grep -q '192.168.1.90'", self.text)
        self.assertNotIn("'bridge=br0' 'hw_mode=a'", rollback)
        self.assertIn("'bridge=br0' 'hw_mode=a'", apply)
        self.assertIn("hostapd_bridge=1", self.text)
        self.assertIn("apply-uapsd-off", self.text)
        self.assertIn("apply-txba-off", self.text)
        self.assertIn('setparam 402 "$txba_disable"', self.text)
        self.assertIn('setparam 402 "$txba_restore"', self.text)
        self.assertIn("get_uapsd:0", self.text)
        self.assertIn("wifi0 uapsd 1", self.text)
        self.assertIn("wpa_key_mgmt=WPA-PSK", self.text)
        self.assertIn("psk=redacted", self.text)

    def test_trial_never_writes_flash_or_bootenv(self) -> None:
        lowered = self.text.lower()
        for forbidden in ("flash_erase", "nandwrite", "mtd_debug write", "saveenv", "fw_setenv"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
