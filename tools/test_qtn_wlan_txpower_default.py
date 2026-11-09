#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211.c"


class QtnWlanTxPowerDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_default_limit_is_not_overwritten_with_radio_kill_value(self) -> None:
        self.assertIn("ic->ic_txpowlimit = IEEE80211_TXPOWER_MAX;", self.text)
        self.assertNotIn("ic->ic_txpowlimit = IEEE80211_TXPOWER_MIN;", self.text)
        self.assertIn("OMQTNTXPWR stage=default-limit", self.text)

    def test_new_limit_starts_at_maximum(self) -> None:
        self.assertIn("ic->ic_newtxpowlimit = IEEE80211_TXPOWER_MAX;", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
