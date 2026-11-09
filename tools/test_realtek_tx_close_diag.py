#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx-close-diag.patch"
APPLY = ROOT / "tools/apply_topaz_linux_510_overlay.sh"
BUILDER = ROOT / "tools/build_realtek_8192ee_incremental.sh"


class RealtekTxCloseDiagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PATCH.read_text(encoding="utf-8")

    def test_explicit_default_off_parameter(self) -> None:
        self.assertIn("static bool hgw500_tx_close_diag;", self.text)
        self.assertIn("module_param_named(hgw500_tx_close_diag", self.text)
        self.assertIn("bool, 0444", self.text)

    def test_target_and_be_queue_gate(self) -> None:
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.text)
        self.assertIn("hw_queue == BE_QUEUE && !ret", self.text)

    def test_observes_both_hardware_indices(self) -> None:
        self.assertIn("cur_tx_rp = (u16)((qidx >> 16) & 0x0fff)", self.text)
        self.assertIn("hw_write_point = (u16)(qidx & 0x0fff)", self.text)

    def test_observes_software_indices_and_ring_size(self) -> None:
        for needle in ("index", "write_point", "ring->entries", "skb_queue_len"):
            self.assertIn(needle, self.text)

    def test_observes_descriptor_ownership(self) -> None:
        self.assertIn("ring->desc[index].dword[0]", self.text)
        self.assertIn("ring->buffer_desc[index].dword[0]", self.text)
        self.assertIn("desc_own=%u bd_own=%u", self.text)

    def test_logging_is_bounded(self) -> None:
        self.assertIn("trace_id <= 16 || is_power_of_2(trace_id)", self.text)
        self.assertIn("queued >= ring->entries - 2", self.text)

    def test_diagnostic_does_not_reclaim_or_write_registers(self) -> None:
        self.assertNotIn("rtl_write_", self.text)
        self.assertNotIn("__skb_dequeue", self.text)
        self.assertNotIn("ring->idx =", self.text)

    def test_build_pipeline_tracks_diagnostic(self) -> None:
        self.assertIn("rtlwifi-mitrastar-tx-close-diag.patch", APPLY.read_text(encoding="utf-8"))
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn("hgw500_tx_close_diag_param", builder)
        self.assertIn('"reclaim_behavior_changed": False', builder)


if __name__ == "__main__":
    unittest.main()
