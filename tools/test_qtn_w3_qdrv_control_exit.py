#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_module.c"


class QdrvControlExitTests(unittest.TestCase):
    def test_control_only_skips_uninitialized_soc_stop(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if (qcb && qcb->resources)", text)
        self.assertIn("OMQDRVEXIT stage=stop-enter", text)
        self.assertIn("OMQDRVEXIT stage=stop-skipped reason=control-only resources=0", text)
        self.assertIn("qdrv_control_input(&qdrv_device, \"stop\", 4)", text)

    def test_exit_lifecycle_is_observable(self):
        text = SOURCE.read_text(encoding="utf-8")
        for marker in (
            "OMQDRVEXIT stage=enter",
            "OMQDRVEXIT stage=control-exit-enter",
            "OMQDRVEXIT stage=control-exit-pass",
            "OMQDRVEXIT stage=complete",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
