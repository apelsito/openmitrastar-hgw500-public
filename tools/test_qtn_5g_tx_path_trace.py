#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_tx.c"


class Qtn5gTxPathTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_trace_is_explicit_and_target_gated(self) -> None:
        self.assertIn("openmitrastar_tx_path_trace_enable", self.text)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.text)
        self.assertIn("module_param(openmitrastar_tx_path_trace_enable, int, 0400)", self.text)

    def test_complete_host_to_muc_chain_is_marked(self) -> None:
        for stage in ("enqueue", "hardstart", "desc-ready", "mailbox-enter", "mailbox-published", "txdone"):
            self.assertIn(f"OMQDRVTXPATH stage={stage}", self.text)

    def test_scheduler_boundary_and_skb_identity_are_marked(self) -> None:
        for stage in ("enqueue-result", "dequeue-enter", "dequeue-blocked", "dequeue-ready"):
            self.assertIn(f"OMQDRVTXPATH stage={stage}", self.text)
        for stage in ("enqueue", "hardstart", "desc-ready", "mailbox-enter", "mailbox-published", "txdone"):
            line = next(
                line for line in self.text.splitlines()
                if f"OMQDRVTXPATH stage={stage}" in line
            )
            self.assertIn("skb=%px", line)

    def test_trace_is_bounded_and_protocol_scoped(self) -> None:
        for counter in (
            "omqdrvtx_enqueue_trace < 32",
            "omqdrvtx_hardstart_trace < 32",
            "omqdrvtx_desc_trace < 32",
            "omqdrvtx_mailbox_trace < 32",
            "omqdrvtx_done_trace < 32",
        ):
            self.assertIn(counter, self.text)
        for proto in ("ETH_P_ARP", "ETH_P_IP", "ETH_P_IPV6"):
            self.assertIn(proto, self.text)
        self.assertNotIn("%pM", self.text[self.text.index("omqdrvtx_trace_active"):self.text.index("static __sram_text void qdrv_tx_skb_return")])

    def test_no_fwt_or_forwarding_behavior_change(self) -> None:
        block = self.text[self.text.index("openmitrastar_tx_path_trace_enable"):]
        self.assertNotIn("topaz_fwt_setup_entry", block)
        self.assertNotIn("w3_fwt_ioss_only_probe_enable", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
