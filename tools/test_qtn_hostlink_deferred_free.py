#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_hostlink.c"


class QtnHostlinkDeferredFreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_irq_free_is_deferred_to_workqueue(self) -> None:
        self.assertIn("struct qdrv_hostlink_deferred_free", self.text)
        self.assertIn("in_interrupt() || irqs_disabled()", self.text)
        self.assertIn("schedule_work(&pending->work)", self.text)
        self.assertIn("qdrv_hostlink_deferred_free_work", self.text)

    def test_dma_free_occurs_in_now_helper(self) -> None:
        start = self.text.index("static void qdrv_hostlink_free_coherent_now")
        end = self.text.index("static void qdrv_hostlink_deferred_free_work", start)
        self.assertIn("dma_free_coherent", self.text[start:end])


if __name__ == "__main__":
    unittest.main(verbosity=2)
