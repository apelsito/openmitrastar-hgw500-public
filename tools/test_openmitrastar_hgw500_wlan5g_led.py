#!/usr/bin/env python3

import hashlib
import pathlib
import struct
import unittest

from elftools.elf.elffile import ELFFile


ROOT = pathlib.Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
PATCH = ROOT / "outputs/kernel-port/hgw500-controls-5g/openmitrastar-wlan5g-led-carrier.patch"
OEM_MONITOR = ROOT / "work/hgw500-rootfs-live/squashfs-root/sbin/monitor_wifi"
OEM_HEADER = ROOT / ".codex_tmp/r5-portable-audit-20260818/src/oem-gpl/buildroot/package/qcsapi/qcsapi-1.0.1/monitor_wifi.h"
EVIDENCE = ROOT / "outputs/kernel-port/hgw500-controls-5g/OEM_WLAN5G_LED_EVIDENCE.md"

OEM_MONITOR_SHA256 = "ffbdb7d3bf3b099a106be532df02595c8eef20da7ace0b27d43bc27746aca734"
LED_ENTRY = struct.Struct("<IIIIiBBBx")


class Hgw500Wlan5gLedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = DRIVER.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.header = OEM_HEADER.read_text(encoding="utf-8")
        cls.evidence = EVIDENCE.read_text(encoding="utf-8")

    def test_exact_oem_monitor_is_pinned(self):
        self.assertEqual(hashlib.sha256(OEM_MONITOR.read_bytes()).hexdigest(),
                         OEM_MONITOR_SHA256)

    def test_oem_binary_wlan_entry_is_gpio1_active_high(self):
        with OEM_MONITOR.open("rb") as stream:
            elf = ELFFile(stream)
            data = elf.get_section_by_name(".data").data()

        # Five 24-byte monitor entries begin after the 8-byte data prefix.
        entries = [LED_ENTRY.unpack_from(data, 8 + i * LED_ENTRY.size)
                   for i in range(5)]
        wps, wlan = entries[:2]
        self.assertEqual((wps[0], wps[1], wps[4], wps[5], wps[6]),
                         (0, 500000, -1, 1, 1))
        self.assertEqual((wlan[0], wlan[1], wlan[4], wlan[5], wlan[6]),
                         (0, 500000, -1, 1, 1))

    def test_gpl_videobridge_contract_corrobates_gpio1(self):
        self.assertIn("defined(CUSTOMER_SPEC_VB)", self.header)
        self.assertIn("#define  MONITOR_WIFI_WLAN_LED_NUMBER\t1", self.header)
        self.assertIn("#define  MONITOR_WIFI_ACTIVE_HIGH\t1", self.header)

    def test_target_and_dts_opt_in_fail_closed(self):
        for marker in (
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            '#define HGW500_WLAN5G_LED_PIN\t1',
            'mitrastar,wlan5g-controls;',
            'mitrastar,wlan5g-led-pin = <1>;',
            'mitrastar,wlan5g-led-active-high;',
            'mitrastar,wlan5g-ifname = "wifi0";',
            '"wlan5g LED must be OEM GPIO1\\n"',
            '"wlan5g interface must be wifi0\\n"',
        ):
            self.assertIn(marker, self.patch)

    def test_led_requires_admin_carrier_operstate_and_ap(self):
        for marker in (
            'netif_running(ndev)',
            'netif_carrier_ok(ndev)',
            'netif_oper_up(ndev)',
            'ndev->ieee80211_ptr->iftype == NL80211_IFTYPE_AP',
            'openmitrastar:green:wlan5g',
            'case NETDEV_CHANGE:',
            'case NETDEV_DOWN:',
            'case NETDEV_UNREGISTER:',
        ):
            self.assertIn(marker, self.patch)

    def test_qdrv_publishes_hostap_run_as_carrier_target_gated(self):
        for marker in (
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            'netif_carrier_off(dev);',
            'vap->iv_opmode == IEEE80211_M_HOSTAP',
            'nstate == IEEE80211_S_RUN',
            'netif_carrier_on(vap->iv_dev);',
            'netif_carrier_off(vap->iv_dev);',
        ):
            self.assertIn(marker, self.patch)

    def test_existing_2g_button_and_recovery_contracts_remain(self):
        for marker in (
            '#define HGW500_WLAN2G_LED_PIN\t11',
            '#define HGW500_WIFI_BUTTON_PIN\t2',
            'openmitrastar:green:wlan2g',
            'qtn,recovery-led-pin = <9>;',
            'qtn,recovery-led-active-low;',
            'mitrastar,wlan2g-led-pin = <11>;',
            'mitrastar,wifi-button-pin = <2>;',
            'mitrastar,stage0-alive-until-userspace-ready;',
            'mitrastar,signalr-led-pin = <7>;',
        ):
            self.assertIn(marker, self.driver + self.dts)

    def test_evidence_records_the_binary_and_policy(self):
        for marker in ("GPIO1", "active-high", "wifi0", "carrier",
                       "operstate", "NL80211_IFTYPE_AP", "No hardware"):
            self.assertIn(marker, self.evidence)


if __name__ == "__main__":
    unittest.main()
