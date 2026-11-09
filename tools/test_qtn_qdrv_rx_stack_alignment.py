#!/usr/bin/env python3
"""Offline contract tests for the MitraStar qdrv RX stack alignment fix."""

from pathlib import Path
import hashlib
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-rxalign-20260820"
PIPELINE = ROOT / "tools/run_qtn_w3_final_5g_open_pipeline.py"
SWITCH_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_RXALIGN_GATE.approved.env"
HOSTLINK_GATE = ROOT / "work/mission-state/w3-offline/W3_QDRV_HOSTLINK_CORE_RXALIGN_GATE.approved.env"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


class QdrvRxStackAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_runtime_and_build_gates_are_target_specific(self) -> None:
        helper = self.source.index("qdrv_rx_stack_align(struct sk_buff *skb, const char *source)")
        gate = self.source.index("omqdrvrx_stack_align_enabled =")
        self.assertLess(helper, gate)
        self.assertIn("#ifdef OPENMITRASTAR_QDRV_V89_PAIR", self.source[:helper])
        self.assertIn(
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            self.source[gate : gate + 300],
        )

    def test_alignment_is_checked_at_ethernet_to_l3_boundary(self) -> None:
        self.assertIn(
            "l3_mod4 = ((unsigned long)skb->data + ETH_HLEN) & 3;",
            self.source,
        )
        self.assertIn(
            "skb_copy_expand(skb, NET_SKB_PAD + NET_IP_ALIGN,",
            self.source,
        )
        for ethernet_mod4 in range(4):
            l3_mod4 = (ethernet_mod4 + 14) & 3
            needs_copy = l3_mod4 != 0
            self.assertEqual(needs_copy, ethernet_mod4 != 2)
        self.assertEqual((2 + 14) & 3, 0)

    def test_copy_precedes_old_skb_release_and_failure_drops_once(self) -> None:
        helper = self.source[
            self.source.index("qdrv_rx_stack_align(struct sk_buff *skb, const char *source)") :
            self.source.index("#else", self.source.index("qdrv_rx_stack_align(struct sk_buff *skb, const char *source)"))
        ]
        copy_at = helper.index("skb_copy_expand")
        success_free_at = helper.rindex("dev_kfree_skb(skb);")
        return_at = helper.rindex("return aligned;")
        self.assertLess(copy_at, success_free_at)
        self.assertLess(success_free_at, return_at)
        self.assertIn("if (unlikely(!aligned))", helper)
        self.assertIn("dev_kfree_skb(skb);\n\t\treturn NULL;", helper)

    def test_realign_preserves_decap_pointer_until_vlan_then_precedes_eth_type_trans(self) -> None:
        callback = self.source[
            self.source.index("qdrv_rx_decap_callback(") :
            self.source.index("static int __sram_text qdrv_rx_data_frm_check")
        ]
        align_at = callback.index('skb = qdrv_rx_stack_align(skb, "decap");')
        vlan_at = callback.index("qdrv_rx_vlan_ingress")
        handle_at = callback.index("if (handle_rx_msdu")
        self.assertLess(vlan_at, align_at)
        self.assertLess(align_at, handle_at)

    def test_direct_tqe_path_realigns_before_stack_delivery(self) -> None:
        handler = self.source[
            self.source.index("qdrv_rx_tqe_rx_handler(") :
            self.source.index("int qdrv_rx_init(")
        ]
        vlan_remove = handler.index("qdrv_rx_remove_eapol_vlan")
        align = handler.index('skb = qdrv_rx_stack_align(skb, "tqe");')
        handle = handler.index("if (handle_rx_msdu")
        stack = handler.index("netif_receive_skb(skb)")
        self.assertLess(vlan_remove, align)
        self.assertLess(align, handle)
        self.assertLess(handle, stack)
        self.assertIn("struct ieee80211_qosframe_addr4 wh_copy", handler)
        self.assertIn("memcpy(&wh_copy, whole_frm_hdr, sizeof(wh_copy))", handler)
        self.assertIn("wh = &wh_copy", handler)
        self.assertNotIn("whole_frm_hdr_offset", handler)
        self.assertLess(handler.index("memcpy(&wh_copy"), align)
        self.assertIn("ieee80211_free_node(ni);\n\t\t\treturn;", handler)

    def test_uart_markers_are_bounded_and_unambiguous(self) -> None:
        for marker in (
            "OMQDRVRX stage=stack-align-gate",
            "OMQDRVRX stage=stack-realign",
            "OMQDRVRX stage=stack-align-drop",
            "OMQDRVRX stage=stack-align-invalid",
            "source=%s",
        ):
            self.assertIn(marker, self.source)
        self.assertRegex(
            self.source,
            re.compile(r"omqdrvrx_stack_align_trace < 8", re.MULTILINE),
        )

    def test_ram_only_pipeline_is_pinned_to_rxalign_artifact(self) -> None:
        pipeline = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("quantenna-linux510-radiohw-rxalign-20260820", pipeline)
        self.assertIn(
            "9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20",
            pipeline,
        )
        self.assertGreaterEqual(pipeline.count('"--rx-align"'), 2)
        self.assertIn('"flash": False', pipeline)

    def test_gate_hashes_bind_exact_25_module_artifact(self) -> None:
        manifest = ARTIFACT / "module-manifest.tsv"
        qdrv = ARTIFACT / (
            "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/"
            "extra/quantenna/qdrv/qdrv.ko"
        )
        switch = env(SWITCH_GATE)
        hostlink = env(HOSTLINK_GATE)
        self.assertEqual(switch["W3_MODULE_MANIFEST_SHA256"], sha256(manifest))
        self.assertEqual(hostlink["W3_MODULE_MANIFEST_SHA256"], sha256(manifest))
        self.assertEqual(hostlink["W3_QDRV_SHA256"], sha256(qdrv))
        self.assertEqual(switch["W3_QDRV_RX_STACK_ALIGN"], "1")
        self.assertEqual(hostlink["W3_QDRV_RX_STACK_ALIGN"], "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
