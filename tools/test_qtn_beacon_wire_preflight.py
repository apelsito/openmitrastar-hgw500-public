#!/usr/bin/env python3
from pathlib import Path
import hashlib
import unittest


ROOT = Path(__file__).resolve().parents[1]
DESC = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_beacon_desc.c"
HEADER = ROOT / "work/linux510-radio-port/quantenna/wlan/openmitrastar_beacon_preflight.h"
QDRV = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-beacon-preflight-20260821"


class BeaconWirePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.desc = DESC.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.qdrv = QDRV.read_text(encoding="utf-8")

    def test_normal_default_is_unchanged_and_gate_is_target_specific(self) -> None:
        self.assertIn("static bool openmitrastar_beacon_preflight_enable;", self.qdrv)
        self.assertIn("module_param(openmitrastar_beacon_preflight_enable, bool, 0400)", self.qdrv)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.qdrv)
        self.assertNotIn("openmitrastar_beacon_preflight_enable = true", self.qdrv)

    def test_preflight_runs_before_beacon_ioctl(self) -> None:
        call = self.qdrv.index("om_ieee80211_beacon_preflight(vap->param")
        ioctl = self.qdrv.index("ioctl->ioctl_command = IOCTL_DEV_BEACON_START", call)
        send = self.qdrv.index("vnet_send_ioctl(qv, ioctl)", ioctl)
        self.assertLess(call, ioctl)
        self.assertLess(ioctl, send)
        fail = self.qdrv.index("OMQDRVBC stage=preflight-fail", call)
        cleanup = self.qdrv.index("qdrv_hostlink_free_coherent", fail)
        self.assertLess(fail, cleanup)
        self.assertLess(cleanup, ioctl)

    def test_all_required_wire_invariants_are_checked(self) -> None:
        for token in (
            "ARRAY_SIZE(visited)",
            "visited[i] == ie",
            "ie_addr < desc_start",
            "ie_addr > desc_end - sizeof(*ie)",
            "!ie->size",
            "total > skb->len - ie->size",
            "buf < skb_start",
            "ie->size > skb_end - buf",
            "plat_kernel_addr_to_dma(NULL, ie->lhost_buf)",
            "plat_kernel_addr_to_dma(NULL, ie->next)",
            "visited[count - 1] != param->tail",
        ):
            self.assertIn(token, self.desc)

    def test_markers_are_bounded_and_include_wire_summary(self) -> None:
        self.assertIn("omqdrv_beacon_preflight_fail_trace < 8", self.qdrv)
        self.assertIn("omqdrv_beacon_preflight_pass_trace < 8", self.qdrv)
        for token in ("reason=%u", "index=%u", "count=%u", "total=%u", "used=%u", "beacon_len=%u", "head_dma=%#x", "args_dma=%#x"):
            self.assertIn(token, self.qdrv)

    def test_shared_wire_prefix_abi_remains_pinned(self) -> None:
        for token in (
            "sizeof(struct beacon_shared_ie_t) != 20",
            "offsetof(struct beacon_shared_ie_t, buf) != 0",
            "offsetof(struct beacon_shared_ie_t, lhost_buf) != 4",
            "offsetof(struct beacon_shared_ie_t, size) != 8",
            "offsetof(struct beacon_shared_ie_t, next_muc_addr) != 12",
            "offsetof(struct beacon_shared_ie_t, next) != 16",
        ):
            self.assertIn(token, self.desc)

    def test_artifact_is_clean_and_hash_bound(self) -> None:
        qdrv = ARTIFACT / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
        wlan = ARTIFACT / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/wlan/wlan.ko"
        self.assertEqual(hashlib.sha256(qdrv.read_bytes()).hexdigest(), "0d9bf9e92231e0db77b8c3320e09f7af40de691086618ab1d83464234f01f982")
        self.assertEqual(hashlib.sha256(wlan.read_bytes()).hexdigest(), "f8449c18a08e46dfe9b9d581bb7eed060d3d260d5e9d36a5364913e3c5b561c8")
        self.assertEqual((ARTIFACT / "depmod-unresolved.log").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
