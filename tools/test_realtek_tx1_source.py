#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
AMPDU_PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx-ampdu-lab.patch"
ACK_PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-honest-tx-ack-lab.patch"


class RealtekTx1SourceTests(unittest.TestCase):
    def test_no_progress_trace_is_bounded(self) -> None:
        text = PCI.read_text(encoding="utf-8")
        self.assertIn("no_progress_count[RTL_PCI_MAX_TX_QUEUE_COUNT]", text)
        self.assertIn("is_power_of_2(no_progress_id)", text)
        self.assertNotIn("trace_id <= 16 || (before && before == after)", text)

    def test_publish_barrier_is_opt_in_and_target_gated(self) -> None:
        text = TRX.read_text(encoding="utf-8")
        self.assertRegex(text, r"static bool hgw500_tx_dma_wmb\s*;")
        self.assertIn("module_param_named(hgw500_tx_dma_wmb", text)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', text)
        self.assertIn("rtlpriv->rtlhal.hw_type == HARDWARE_TYPE_RTL8192EE", text)
        self.assertRegex(
            text,
            re.compile(
                r"if \(tx_dma_wmb\).*?dma_wmb\(\);\s*}\s*"
                r"rtl_write_word\(rtlpriv, desc_address, ring->cur_tx_wp\);",
                re.S,
            ),
        )

    def test_close_diag_stays_opt_in(self) -> None:
        text = TRX.read_text(encoding="utf-8")
        self.assertRegex(text, r"static bool hgw500_tx_close_diag\s*;")
        self.assertIn("module_param_named(hgw500_tx_close_diag", text)
        self.assertIn("OMRTLTXCLOSE", text)
        self.assertIn("close_diag_max_queued", text)
        self.assertIn("high_water_edge", text)
        self.assertNotIn("is_power_of_2(trace_id) ||\n\t\t    queued >=", text)

    def test_ampdu_and_ack_experiments_remain_default_off(self) -> None:
        ampdu = AMPDU_PATCH.read_text(encoding="utf-8")
        ack = ACK_PATCH.read_text(encoding="utf-8")
        self.assertRegex(ampdu, r"static bool hgw500_tx_ampdu_disable\s*;")
        self.assertRegex(ack, r"bool rtl_hgw500_honest_tx_ack\s*;")


if __name__ == "__main__":
    unittest.main()
