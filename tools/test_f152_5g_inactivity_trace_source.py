#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_node.c"


class F152InactivityTraceSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_trace_is_target_gated_bounded_and_mac_free(self) -> None:
        self.assertIn("#ifdef OPENMITRASTAR_QDRV_V89_PAIR", self.text)
        self.assertIn("omqtn_inact_trace < 128", self.text)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.text)
        marker = next(line for line in self.text.splitlines() if "OMQTNINACT seq=" in line)
        self.assertNotIn("%pM", marker)

    def test_original_inactivity_decision_is_preserved(self) -> None:
        self.assertIn("if ((rx_now != ni->rx_pkts) || (ack_now != ni->tx_acks))", self.text)
        self.assertIn("ni->ni_inact = ni->ni_inact_reload;", self.text)
        self.assertIn("ni->ni_inact--;", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
