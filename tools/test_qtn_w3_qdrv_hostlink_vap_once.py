#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/qtn_w3_qdrv_hostlink_vap_once_remote.sh"


class HostlinkVapOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_requires_cmd19_before_cmd4(self):
        self.assertLess(self.text.index("cmd=19"), self.text.index("start 0 ap wifi0"))

    def test_requires_nonzero_publish_and_done(self):
        self.assertIn("cmd=4 .*published=0x4", self.text)
        self.assertIn("cmd=4 .*rc=1", self.text)

    def test_keeps_rf_closed_and_wifi_down(self):
        self.assertIn('test "$(cat "$rf")" = 0', self.text)
        self.assertIn('test "$(cat /sys/class/net/wifi0/operstate)" = down', self.text)
        self.assertNotIn("openmitrastar_rf_enable=1", self.text)

    def test_no_flash_or_module_unload(self):
        lowered = self.text.lower()
        for forbidden in ("flash_erase", "mtd write", "saveenv", "rmmod"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
