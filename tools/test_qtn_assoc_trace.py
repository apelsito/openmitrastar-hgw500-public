#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
QDRV_RX = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c"
INPUT = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_input.c"
NODE = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_node.c"
OUTPUT = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_output.c"
LINUX = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_linux.c"


class AssocTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rx = QDRV_RX.read_text(encoding="utf-8")
        cls.input = INPUT.read_text(encoding="utf-8")
        cls.node = NODE.read_text(encoding="utf-8")
        cls.output = OUTPUT.read_text(encoding="utf-8")
        cls.linux = LINUX.read_text(encoding="utf-8")

    def test_all_stages_are_bounded_and_hgw_gated(self) -> None:
        sources = "\n".join((self.rx, self.input, self.node, self.output, self.linux))
        for stage in (
            "rx-decap", "auth-open-rx", "auth-open-response",
            "assoc-request", "node-join-call", "node-join-enter",
            "mgmt-tx", "iwev-registered",
        ):
            self.assertIn(f"OMQDRVASSOC stage={stage}", sources)
        self.assertGreaterEqual(
            sources.count('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")'),
            8,
        )
        self.assertGreaterEqual(sources.count("< 32"), 8)

    def test_trace_does_not_log_client_mac(self) -> None:
        for source in (self.rx, self.input, self.node, self.output, self.linux):
            for line in source.splitlines():
                if "OMQDRVASSOC stage=" in line:
                    self.assertNotIn("%pM", line)
                    self.assertNotIn("DBGMAC", line)

    def test_bss_false_client_event_is_suppressed(self) -> None:
        start = self.node.index("void\nieee80211_node_authorize")
        end = self.node.index("EXPORT_SYMBOL(ieee80211_node_authorize)", start)
        block = self.node[start:end]
        self.assertIn("ni == ni->ni_vap->iv_bss", block)
        self.assertIn("ni->ni_vap->iv_opmode != IEEE80211_M_STA", block)
        self.assertIn("event_addr = ni->ni_macaddr", block)
        self.assertIn("event_addr = ni->ni_bssid", block)
        self.assertIn("ETHERFMT(event_addr)", block)

    def test_trace_order_covers_rx_to_wext(self) -> None:
        self.assertLess(self.input.index("OMQDRVASSOC stage=assoc-request"),
                        self.input.index("OMQDRVASSOC stage=node-join-call"))
        self.assertLess(self.node.index("OMQDRVASSOC stage=node-join-enter"),
                        self.node.index("ieee80211_notify_node_join(ni, newassoc)"))
        self.assertLess(self.linux.index("OMQDRVASSOC stage=iwev-registered"),
                        self.linux.index("wireless_send_event(dev, IWEVREGISTERED"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
