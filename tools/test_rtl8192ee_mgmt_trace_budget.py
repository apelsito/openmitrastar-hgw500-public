#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = (
    ROOT
    / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
)


class Rtl8192eeMgmtTraceBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = TRX.read_text(encoding="utf-8")

    def test_rx_and_tx_have_per_subtype_counters(self) -> None:
        self.assertIn("static bool hgw500_mgmt_trace;", self.source)
        self.assertIn("module_param_named(hgw500_mgmt_trace", self.source)
        self.assertIn("if (!hgw500_mgmt_trace)", self.source)
        self.assertIn(
            "hgw500_mgmt_rx_trace_count[HGW500_MGMT_TRACE_CLASS_MAX]",
            self.source,
        )
        self.assertIn(
            "hgw500_mgmt_tx_trace_count[HGW500_MGMT_TRACE_CLASS_MAX]",
            self.source,
        )
        self.assertIn("n = ++counters[trace_class];", self.source)
        self.assertNotIn("&hgw500_mgmt_rx_trace_count", self.source)
        self.assertNotIn("&hgw500_mgmt_tx_trace_count", self.source)

    def test_join_critical_subtypes_have_independent_classes(self) -> None:
        for token in (
            "HGW500_MGMT_AUTH",
            "HGW500_MGMT_ASSOC_REQ",
            "HGW500_MGMT_ASSOC_RESP",
            "HGW500_MGMT_REASSOC_REQ",
            "HGW500_MGMT_REASSOC_RESP",
            "HGW500_MGMT_DEAUTH",
            "HGW500_MGMT_DISASSOC",
        ):
            self.assertIn(token, self.source)

    def test_probe_budget_is_lower_without_consuming_join_budget(self) -> None:
        self.assertIn("initial_limit = trace_class == HGW500_MGMT_PROBE_REQ", self.source)
        self.assertIn("HGW500_MGMT_PROBE_RESP ? 16 : 64", self.source)
        self.assertNotIn("static unsigned int hgw500_mgmt_rx_trace_count;", self.source)
        self.assertNotIn("static unsigned int hgw500_mgmt_tx_trace_count;", self.source)


if __name__ == "__main__":
    unittest.main()
