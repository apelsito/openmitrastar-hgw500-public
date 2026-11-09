#!/usr/bin/env python3
"""Offline contract for bounded, privacy-preserving Q3 management RX traces."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c"


class AssocRxObservabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_target_and_abi_gated(self) -> None:
        block = self.source.split("OMQDRVRXMGMT stage=frame", 1)[0][-2500:]
        self.assertIn("#ifdef OPENMITRASTAR_QDRV_V89_PAIR", block)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', block)

    def test_trace_is_bounded_and_covers_probe_auth_assoc(self) -> None:
        self.assertIn("omqdrvrx_mgmt_trace < 64", self.source)
        self.assertIn("IEEE80211_FC0_SUBTYPE_PROBE_REQ", self.source)
        self.assertIn("IEEE80211_FC0_SUBTYPE_AUTH", self.source)
        self.assertIn("IEEE80211_FC0_SUBTYPE_ASSOC_REQ", self.source)
        self.assertIn("OMQDRVRXMGMT stage=summary", self.source)
        self.assertIn("30 * HZ", self.source)

    def test_trace_does_not_log_station_addresses(self) -> None:
        frame = self.source.split('pr_info("OMQDRVRXMGMT stage=frame', 1)[1].split(");", 1)[0]
        self.assertNotIn("%pM", frame)
        self.assertNotIn("i_addr2", frame)


if __name__ == "__main__":
    unittest.main()
