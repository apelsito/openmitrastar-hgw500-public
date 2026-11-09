#!/usr/bin/env python3
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOC = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.c"


def topaz_wire_bus(original_dma: int, size: int) -> int:
    dram_cached = 0x80000000
    dram_size = 0x08000000
    if original_dma >> 32:
        raise ValueError("width")
    if dram_cached <= original_dma < dram_cached + dram_size:
        wire = original_dma - dram_cached
    else:
        wire = 0
    if wire == 0 or wire >= dram_size or size > dram_size - wire:
        raise ValueError("range")
    return wire


class SharedParamsWireBusTests(unittest.TestCase):
    def test_live_style_high_alias_becomes_low_topaz_bus(self):
        self.assertEqual(topaz_wire_bus(0x84F60000, 0x77A0), 0x04F60000)
        self.assertLess(topaz_wire_bus(0x84F60000, 0x77A0) + 0x77A0, 0x08000000)

    def test_invalid_aliases_and_overflow_fail_closed(self):
        for dma, size in ((0, 0x77A0), (0x08000000, 0x77A0),
                          (0x88000000, 0x77A0), (0x87FFF000, 0x2000),
                          (0x1_84F60000, 0x77A0)):
            with self.assertRaises(ValueError):
                topaz_wire_bus(dma, size)

    def test_source_keeps_dma_and_wire_identities_separate(self):
        text = SOC.read_text()
        self.assertRegex(text, re.compile(r"dma_alloc_coherent\([^;]+&original_dma", re.S))
        self.assertRegex(text, re.compile(r"wire_bus\s*=.*virt_to_bus", re.S))
        self.assertIn("qtn_mproc_sync_shared_params_set((struct shared_params*)params_bus)", text)
        self.assertIn("params_dma_handle);", text)
        self.assertNotIn("qtn_mproc_sync_shared_params_set((struct shared_params*)original_dma)", text)


if __name__ == "__main__":
    unittest.main()
