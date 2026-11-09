#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VAP = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_vap.c"
WLAN = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"
HEADER = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_vap.h"


class BeaconCallpathInstrumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vap = VAP.read_text(encoding="utf-8")
        cls.wlan = WLAN.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")

    def test_gate_default_remains_off(self) -> None:
        self.assertIn("static bool openmitrastar_beacon_preflight_enable;", self.wlan)
        self.assertNotIn("openmitrastar_beacon_preflight_enable = true", self.wlan)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.wlan)

    def test_every_entry_and_early_return_is_observable(self) -> None:
        entry = self.wlan.index("OMQDRVBC stage=entry")
        not_running = self.wlan.index("OMQDRVBC stage=early-return reason=not-running")
        channel_any = self.wlan.index("OMQDRVBC stage=early-return reason=channel-any")
        wds = self.wlan.index("OMQDRVBC stage=early-return reason=wds")
        self.assertLess(entry, not_running)
        self.assertLess(not_running, channel_any)
        self.assertLess(channel_any, wds)
        self.assertIn("omqdrv_beacon_entry_trace < 16", self.wlan)

    def test_diagnostic_path_defers_until_parent_and_carrier_publication(self) -> None:
        defer = self.vap.index("OMQDRVBC stage=callsite-deferred")
        parent = self.vap.index("error = (*qv->qv_newstate)", defer)
        carrier = self.vap.index("netif_carrier_on", parent)
        post_parent = self.vap.index("OMQDRVBC stage=callsite-post-parent", carrier)
        retry = self.vap.index("ic->ic_beacon_update(vap)", post_parent)
        self.assertLess(defer, parent)
        self.assertLess(parent, carrier)
        self.assertLess(carrier, post_parent)
        self.assertLess(post_parent, retry)
        self.assertIn("beacon_ioctl_after == beacon_ioctl_before", self.vap)

    def test_normal_gate_closed_path_keeps_original_pre_parent_call(self) -> None:
        hostap = self.vap.index("case IEEE80211_M_HOSTAP:")
        parent = self.vap.index("error = (*qv->qv_newstate)", hostap)
        original_call = self.vap.index("ic->ic_beacon_update(vap)", hostap)
        self.assertLess(original_call, parent)
        self.assertIn("if (beacon_preflight)", self.vap[hostap:original_call])
        self.assertIn("else", self.vap[hostap:original_call])

    def test_ioctl_count_marks_actual_muc_submission_and_is_bounded(self) -> None:
        count = self.wlan.index("WRITE_ONCE(omqdrv_beacon_ioctl_count")
        marker = self.wlan.index("OMQDRVBC stage=ioctl-send", count)
        send = self.wlan.index("vnet_send_ioctl(qv, ioctl)", marker)
        self.assertLess(count, marker)
        self.assertLess(marker, send)
        self.assertIn("ioctl_count <= 16", self.wlan[count:marker])
        self.assertIn("qdrv_openmitrastar_beacon_ioctl_count", self.header)

    def test_callpath_patch_does_not_introduce_fwt(self) -> None:
        changed_region = self.vap[self.vap.index("OMQDRVBC stage=callsite-deferred"):]
        self.assertNotIn("fwt_ctrl", changed_region)


if __name__ == "__main__":
    unittest.main(verbosity=2)
