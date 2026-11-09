#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/compat/include/openmitrastar_qdrv_compat.h"


class QtnBridgeSubportMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_map_sets_the_node_validity_bit(self) -> None:
        self.assertIn("#define BR_SUBPORT_MAP(port) ((port) | 0x8000U)", self.text)

    def test_unmap_removes_only_the_validity_bit(self) -> None:
        self.assertIn("#define BR_SUBPORT_UNMAP(port) ((port) & 0x7fffU)", self.text)

    def test_mapping_round_trip(self) -> None:
        for node in (0, 1, 4, 5, 127):
            mapped = node | 0x8000
            self.assertNotEqual(0, mapped & 0x8000)
            self.assertEqual(node, mapped & 0x7FFF)


if __name__ == "__main__":
    unittest.main(verbosity=2)
