#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOSTLINK = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_hostlink.c"


class QdrvHostlinkWireDmaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HOSTLINK.read_text(encoding="utf-8")

    def test_fix_is_exact_target_and_pair_gated(self):
        self.assertIn("OPENMITRASTAR_QDRV_V89_PAIR", self.text)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.text)

    def test_allocation_converts_original_to_wire_then_muc_nocache(self):
        self.assertIn("original_dma = *dma_handle", self.text)
        self.assertIn("qdrv_dma_handle_to_wire(original_dma, size, &wire_bus)", self.text)
        self.assertIn("muc_to_nocache", self.text)
        self.assertIn('OMQDRVHLINK stage=alloc-pass', self.text)

    def test_failed_conversion_frees_original_handle(self):
        self.assertIn("dma_free_coherent(dev, size, ret, original_dma)", self.text)
        self.assertIn("*dma_handle = 0", self.text)

    def test_free_performs_exact_inverse(self):
        self.assertIn("wire_bus = (u32)(unsigned long)nocache_to_muc", self.text)
        self.assertIn("original_dma = (dma_addr_t)(unsigned long)bus_to_virt(wire_bus)", self.text)
        self.assertIn("dma_free_coherent(dev, size, kvaddr, original_dma)", self.text)

    def test_markers_are_bounded(self):
        self.assertIn("omhlink_alloc_trace < 8", self.text)
        self.assertIn("omhlink_free_trace < 8", self.text)
        self.assertIn("omhlink_publish_trace < 8", self.text)
        self.assertIn("omhlink_complete_trace < 8", self.text)
        self.assertIn('OMQDRVHLINK stage=publish', self.text)
        self.assertIn('OMQDRVHLINK stage=complete', self.text)


if __name__ == "__main__":
    unittest.main()
