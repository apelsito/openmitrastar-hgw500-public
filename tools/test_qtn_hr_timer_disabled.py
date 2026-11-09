#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"


class QtnHrTimerDisabledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_hgw_target_returns_before_timer_is_armed(self) -> None:
        start = self.text.index("static void qdrv_wlan_hr_oneshot_enable")
        end = self.text.index("static void\nqdrv_wlan_hr_oneshot_disable", start)
        body = self.text[start:end]

        guard = body.index('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")')
        marker = body.index("OMQDRVHR stage=timer-disabled reason=hgw-v89")
        early_return = body.index("return;", marker)
        timer_setup = body.index("timer_setup", early_return)
        mod_timer = body.index("mod_timer", timer_setup)

        self.assertLess(guard, marker)
        self.assertLess(marker, early_return)
        self.assertLess(early_return, timer_setup)
        self.assertLess(timer_setup, mod_timer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
