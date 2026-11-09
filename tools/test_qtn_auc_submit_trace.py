#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_tx.c"


class QtnAucSubmitTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_auc_trace_records_hardware_submission_result(self) -> None:
        self.assertIn("OMQDRVTXPATH stage=auc-submit", self.text)
        for field in (
            "dest_port=%u", "node=%u", "port=%u", "tid=%u",
            "use4=%u", "rc=%d", "busy=%u",
        ):
            self.assertIn(field, self.text)

    def test_trace_preserves_existing_busy_drop_behavior(self) -> None:
        trace = self.text.index("OMQDRVTXPATH stage=auc-submit")
        busy = self.text.index("if (tqe_queued == NETDEV_TX_BUSY)", trace)
        free = self.text.index("kfree_skb(skb);", busy)
        self.assertLess(trace, busy)
        self.assertLess(busy, free)


if __name__ == "__main__":
    unittest.main(verbosity=2)
