#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_tx.c"


class QtnNodeSchedulerTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_trace_captures_node_qdisc_and_quota_state(self) -> None:
        self.assertIn("OMQDRVTXPATH stage=node-enqueue-result", self.text)
        for field in (
            "node_qdisc=%px", "active_qdisc=%px", "installed_qdisc=%px",
            "same_active=%u", "same_installed=%u", "muc=%u",
            "thresh=%u/%u", "over=%u/%u", "used=%u/%u",
            "node_qlen=%u/%u", "queued=%u", "active_bands=%u",
            "root_qlen=%u",
        ):
            self.assertIn(field, self.text)

    def test_trace_does_not_change_quota_decision(self) -> None:
        self.assertIn("is_over_quota = qdrv_tx_nd_is_over_quota(qw, ni);", self.text)
        self.assertIn("qdrv_sch_enqueue_node(&ni->ni_tx_sch, skb,", self.text)
        self.assertIn("is_over_quota,", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
