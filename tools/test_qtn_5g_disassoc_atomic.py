#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"


class QtnDisassocAtomicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")
        start = cls.text.index("static void qdrv_wlan_80211_disassoc")
        end = cls.text.index("static void qdrv_wlan_qtnie_parse", start)
        cls.block = cls.text[start:end]

    def test_disassoc_uses_atomic_dma_allocation(self) -> None:
        self.assertIn("GFP_DMA | GFP_ATOMIC", self.block)
        self.assertNotIn("GFP_DMA | GFP_KERNEL", self.block)

    def test_change_is_limited_to_the_allocation_flag(self) -> None:
        self.assertEqual(1, self.block.count("qdrv_hostlink_alloc_coherent"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
