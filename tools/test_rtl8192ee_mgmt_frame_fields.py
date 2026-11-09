#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"


class Rtl8192eeMgmtFrameFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = TRX.read_text(encoding="utf-8")

    def test_rx_and_tx_markers_include_management_body_words(self) -> None:
        self.assertGreaterEqual(self.source.count("body0=%04x body1=%04x body2=%04x"), 2)
        for offset in (24, 26, 28):
            self.assertGreaterEqual(self.source.count(f"get_unaligned_le16(frame + {offset})"), 2)

    def test_tx_marker_includes_compact_txbds(self) -> None:
        for token in ("b0=%08x", "b1=%08x", "b2=%08x", "b3=%08x", "b4=%08x", "b5=%08x"):
            self.assertIn(token, self.source)
        self.assertIn("buffer_desc_stride >= 24", self.source)


if __name__ == "__main__":
    unittest.main()
