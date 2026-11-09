#!/usr/bin/env python3
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "tools/build_quantenna_linux510.sh"


class QuantennaNullDmaGateTests(unittest.TestCase):
    def test_gate_covers_dma_pools_as_well_as_mapping_apis(self):
        text = BUILD.read_text(encoding="utf-8")
        self.assertIn("dma_pool_create", text)
        self.assertIn("dma_(alloc|free)_coherent", text)
        self.assertIn("dma_(map|unmap)_single", text)

    def test_current_source_has_no_null_pool_device(self):
        source = (ROOT / "work/linux510-radio-port/quantenna").read_text if False else None
        offenders = []
        pattern = re.compile(r"dma_pool_create\s*\([^,]+,\s*NULL")
        for path in (ROOT / "work/linux510-radio-port/quantenna").rglob("*.[ch]"):
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [], offenders)


if __name__ == "__main__":
    unittest.main()
