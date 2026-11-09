#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_control.c"


class QtnSequentialReadonlyGetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_get_is_allowed_before_started_rejection(self) -> None:
        start = self.text.index("static int qdrv_sequential_precheck")
        end = self.text.index("static void qdrv_sequential_note_success", start)
        body = self.text[start:end]
        allow = body.index('if (!strcmp(argv[0], "get"))')
        started = body.index("if (openmitrastar_sequential_started)")
        self.assertLess(allow, started)

    def test_mutating_commands_remain_guarded(self) -> None:
        start = self.text.index("static int qdrv_sequential_precheck")
        end = self.text.index("static void qdrv_sequential_note_success", start)
        body = self.text[start:end]
        self.assertIn('if (!strcmp(argv[0], "set"))', body)
        self.assertIn('if (!strcmp(argv[0], "clearsram"))', body)
        self.assertIn('if (!strcmp(argv[0], "start"))', body)
        self.assertIn("reason=command-not-allowlisted", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
