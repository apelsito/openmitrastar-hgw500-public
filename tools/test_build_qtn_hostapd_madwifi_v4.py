#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "tools/build_qtn_hostapd_madwifi_v4.sh"
CONFIG = ROOT / "work/mission-state/w3-offline/hostapd-qtn-madwifi-v4.config"
MADWIFI_SOURCE = ROOT / (
    "work/sources/Quantenna-GPL/buildroot/package/zhostapd/"
    "hostapd-git/src/drivers/driver_madwifi.c"
)


class QtnHostapdBuildTests(unittest.TestCase):
    def test_madwifi_wpa2_ccmp_profile(self):
        text = CONFIG.read_text(encoding="utf-8")
        self.assertIn("CONFIG_DRIVER_MADWIFI=y", text)
        self.assertIn("CONFIG_NO_TKIP=y", text)
        self.assertIn("CONFIG_TLS=internal", text)
        self.assertIn("CONFIG_WPS=y", text)
        self.assertIn("CONFIG_WPS_UPNP=y", text)
        self.assertIn("NO_SHA256_WRAPPER", text)

    def test_noatomic_static_abi_gates(self):
        text = BUILD.read_text(encoding="utf-8")
        self.assertIn("-mno-atomic", text)
        self.assertIn("-static", text)
        self.assertIn("llock|scond", text)
        self.assertIn("Flags:.*0x403", text)

    def test_source_and_headers_are_pinned_local(self):
        text = BUILD.read_text(encoding="utf-8")
        self.assertIn("Quantenna-GPL/buildroot/package/zhostapd/hostapd-git", text)
        self.assertIn("drivers/include/shared", text)
        self.assertIn("zhostapd/madwifi", text)

    def test_gcc15_bool_collision_is_isolated_to_build_copy(self):
        text = BUILD.read_text(encoding="utf-8")
        self.assertIn("bool_txt(Boolean value)", text)
        self.assertIn("return value ?", text)
        self.assertIn("wpa_bool_txt(int value)", text)
        self.assertIn("nanosleep", text)

    def test_broadcast_flush_waits_for_up_and_running(self):
        text = MADWIFI_SOURCE.read_text(encoding="utf-8")
        self.assertIn("OMHAPD flush-skip", text)
        self.assertIn("IFF_UP | IFF_RUNNING", text)
        for index in range(6):
            self.assertIn(f"addr[{index}] == 0xff", text)

    def test_private_ioctl_failure_preserves_visible_errno(self):
        text = MADWIFI_SOURCE.read_text(encoding="utf-8")
        self.assertIn("int saved_errno = errno;", text)
        self.assertIn("OMHAPD ioctl-failed", text)
        self.assertIn("errno = saved_errno;", text)

    def test_raw_probe_socket_falls_back_to_bss_interface_without_bridge(self):
        text = MADWIFI_SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "hapd->conf->bridge[0] ? hapd->conf->bridge : bss->ifname",
            text,
        )
        self.assertIn("OMHAPD raw-probe-socket", text)
        self.assertNotIn(
            "l2_packet_init(hapd->conf->bridge, NULL, ETH_P_80211_RAW",
            text,
        )


if __name__ == "__main__":
    unittest.main()
