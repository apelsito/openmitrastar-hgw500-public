#!/usr/bin/env python3
from pathlib import Path
import hashlib
import os
import unittest


ROOT = Path(__file__).resolve().parents[1]
QDRV = ROOT / "work/linux510-radio-port/quantenna/qdrv"
CONTROL = QDRV / "qdrv_control.c"
WLAN = QDRV / "qdrv_wlan.c"
HOSTLINK = QDRV / "qdrv_hostlink.c"
HEADER = QDRV / "qdrv_wlan.h"
VAP = QDRV / "qdrv_vap.c"
SOC = QDRV / "qdrv_soc.c"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-powerselect-seq-f46-20260825"
RELEASE = "5.10.260-openmitrastar-radiohw"
ASSOC_QDRV = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-assoc-rx-v2"
    / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko"
)
START = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BeaconLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.control = CONTROL.read_text(encoding="utf-8")
        cls.wlan = WLAN.read_text(encoding="utf-8")
        cls.hostlink = HOSTLINK.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.vap = VAP.read_text(encoding="utf-8")
        cls.soc = SOC.read_text(encoding="utf-8")
        cls.start = START.read_text(encoding="utf-8")

    def test_callback_only_queues_process_context_work(self) -> None:
        start = self.wlan.index("static void qdrv_wlan_80211_beacon_update(")
        end = self.wlan.index("void qdrv_wlan_beacon_vap_detach", start)
        callback = self.wlan[start:end]
        self.assertIn("schedule_work(&txn->work)", callback)
        self.assertNotIn("ieee80211_beacon_create_param", callback)
        self.assertNotIn("vnet_send_ioctl", callback)

    def test_worker_owns_all_muc_referenced_payloads(self) -> None:
        for token in (
            "struct host_ioctl *ioctl",
            "struct qtn_beacon_args *args",
            "struct ieee80211_beacon_param_t *param",
            "struct sk_buff *skb",
            "QDRV_BEACON_TXN_QUARANTINED",
        ):
            self.assertIn(token, self.header)
        self.assertIn("txn->param = vap->param", self.wlan)
        self.assertIn("vap->param = NULL", self.wlan)
        self.assertIn("txn->skb = beacon_skb", self.wlan)

    def test_only_done_err_or_stopped_muc_release_quarantine(self) -> None:
        self.assertIn("QTN_HLINK_RC_DONE | QTN_HLINK_RC_ERR", self.wlan)
        self.assertIn("!muc_stopped && !qdrv_wlan_beacon_ioctl_acked", self.wlan)
        self.assertIn("qdrv_wlan_beacon_purge(qw)", self.wlan)
        self.assertLess(self.soc.index("qdrv_muc_exit(qcb)"), self.soc.index("qdrv_wlan_exit(&qcb->macs[0])"))
        self.assertLess(self.wlan.index("qdrv_wlan_beacon_purge(qw)"), self.wlan.index("qdrv_hostlink_exit(qw)"))

    def test_published_timeout_keeps_hostlink_slot(self) -> None:
        timeout = self.hostlink.index("hlink_timeout:")
        tail = self.hostlink[timeout:self.hostlink.index("void* qdrv_hostlink_alloc_coherent", timeout)]
        self.assertIn("retain_published_timeout && published", tail)
        self.assertIn("*retained = true", tail)
        self.assertIn("stage=quarantine", tail)
        self.assertIn("vnet_send_ioctl_owned", self.hostlink)

    def test_beacon_completion_reports_done_and_err_bits(self) -> None:
        self.assertIn("OMQDRVHLINK stage=beacon-complete", self.hostlink)
        self.assertIn("IOCTL_DEV_BEACON_START", self.hostlink)
        self.assertIn("QTN_HLINK_RC_DONE", self.hostlink)
        self.assertIn("QTN_HLINK_RC_ERR", self.hostlink)
        self.assertIn("OMQDRVBC stage=ioctl-return", self.wlan)

    def test_mailbox_is_rechecked_and_doorbell_is_serialized(self) -> None:
        publish = self.hostlink.index("wait_empty_mbox:")
        complete = self.hostlink.index('desc = "waiting for MuC dequeue"', publish)
        block = self.hostlink[publish:complete]
        self.assertIn("spin_lock_irqsave(&qw->flowlock", block)
        self.assertIn("if (*mbox)", block)
        self.assertIn("goto wait_empty_mbox", block)
        self.assertLess(block.index("WRITE_ONCE(*mbox, published_ioctl)"), block.index("qdrv_mac_interrupt_muc"))
        self.assertLess(block.index("qdrv_mac_interrupt_muc"), block.rindex("spin_unlock_irqrestore"))

    def test_vap_teardown_cancels_worker_without_freeing_quarantine(self) -> None:
        self.assertIn("qdrv_wlan_beacon_vap_detach(qv)", self.vap)
        detach = self.wlan[self.wlan.index("void qdrv_wlan_beacon_vap_detach"):]
        self.assertIn("cancel_work_sync(&txn->work)", detach)
        self.assertNotIn("qdrv_wlan_beacon_txn_release(txn, true)", detach.split("static void qdrv_wlan_beacon_purge", 1)[0])

    def test_built_modules_are_hash_bound_and_depmod_clean(self) -> None:
        qdrv = ASSOC_QDRV
        wlan = ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/wlan/wlan.ko"
        qdrv = ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko"
        self.assertEqual(sha(qdrv), "37527d16fa93325b676fde7247314fa0a9179095f3e6a7eb8dc19c63962b6f5f")
        self.assertEqual(sha(wlan), "09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872")
        self.assertEqual((ARTIFACT / "depmod-unresolved.log").read_bytes(), b"")

    def test_lifetime_profile_waits_bounded_for_queued_beacon(self) -> None:
        start = self.start.index('if [ "$beacon_v89_wire_enable" = 1 ]; then', self.start.index("hostapd-pid-mismatch"))
        end = self.start.index('if [ "$qdrv_profile" = current-rc1-cf02 ]; then', start)
        wait = self.start[start:end]
        self.assertIn('[ "$beacon_lifetime_wait" -lt 15 ]', wait)
        self.assertIn("hostapd-died-waiting-beacon-lifetime", wait)
        self.assertIn("hostapd-pong-lost-waiting-beacon-lifetime", wait)
        self.assertIn("rf-lost-waiting-beacon-lifetime", wait)
        self.assertIn("beacon-lifetime-fatal-during-wait", wait)
        self.assertIn("OMQDRVBC stage=preflight-pass", wait)
        self.assertIn("OMQDRVBC stage=ioctl-send", wait)
        self.assertIn("beacon-lifetime-markers-timeout", wait)
        generic = self.start.index('if [ "$beacon_preflight_enable" = 1 ]; then', end)
        self.assertGreater(generic, end)

    def test_lifetime_profile_pins_and_enables_v89_wire_modules(self) -> None:
        branch = self.start[
            self.start.index('if [ "$beacon_lifetime_value" = Q3_RADIO5_BEACON_LIFETIME=1 ]; then'):
            self.start.index("psk=", self.start.index('if [ "$beacon_lifetime_value" = Q3_RADIO5_BEACON_LIFETIME=1 ]; then'))
        ]
        defaults = self.start[
            self.start.index("qdrv_profile=current-rc1-cf02"):
            self.start.index('qdrv9_value=$(sed', self.start.index("qdrv_profile=current-rc1-cf02"))
        ]
        self.assertIn("beacon_preflight_enable=1", defaults)
        self.assertIn("beacon_v89_wire_enable=1", defaults)
        expected_qdrv = os.environ.get(
            "OM_Q3_EXPECTED_BEACON_LIFETIME_QDRV_SHA256",
            "a6f0bdc8e6cf40c1f140c4c8843b2ca4e61e55bcc6b93af8ac52d6496d43f882",
        )
        self.assertIn(f"expected_qdrv_sha={expected_qdrv}", branch)
        self.assertIn("expected_wlan_sha=09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872", branch)
        self.assertIn("beacon_preflight_enable=1", branch)
        self.assertIn("beacon_v89_wire_enable=1", branch)

    def test_power_selection_is_allowed_in_guarded_sequence(self) -> None:
        self.assertIn("OMQDRVSEQ_SET_POWER_SELECTION", self.control)
        self.assertIn('!strcmp(name, "power_selection")', self.control)
        self.assertIn("OMQDRVSEQ_SET_POWER_SELECTION)", self.control)
        self.assertIn('strcmp(argv[2], "2")', self.control)
        self.assertIn(
            "openmitrastar_sequential_mask != OMQDRVSEQ_ALL_MASK",
            self.control,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
