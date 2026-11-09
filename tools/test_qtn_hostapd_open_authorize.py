#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/sources/Quantenna-GPL/buildroot/package/zhostapd/hostapd-git/src/ap/drv_callbacks.c"


class OpenAuthorizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_driver_event_open_bss_authorizes_kernel_node(self) -> None:
        start = self.text.index("int hostapd_notif_assoc")
        end = self.text.index("void hostapd_notif_disassoc", start)
        block = self.text[start:end]
        assoc = block.index("sta->flags |= WLAN_STA_AUTH | WLAN_STA_ASSOC")
        authorize = block.index("hostapd_set_authorized(hapd, sta, 1)")
        notify = block.index("hostapd_new_assoc_sta(hapd, sta", authorize)
        self.assertLess(assoc, authorize)
        self.assertLess(authorize, notify)
        self.assertIn("!hapd->conf->ieee802_1x && !hapd->conf->wpa", block)
        self.assertIn("OMHAPD open-authorize path=driver-event", block)

    def test_secure_bss_is_not_force_authorized(self) -> None:
        block = self.text[self.text.index("int hostapd_notif_assoc"):]
        gate = block.index("!hapd->conf->ieee802_1x && !hapd->conf->wpa")
        authorize = block.index("hostapd_set_authorized(hapd, sta, 1)", gate)
        self.assertLess(gate, authorize)


if __name__ == "__main__":
    unittest.main(verbosity=2)
