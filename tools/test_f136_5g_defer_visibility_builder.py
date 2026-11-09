from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f133_5g_disable_hr_timer_from_f132 as f133  # noqa: E402
import build_f136_5g_defer_post_hostapd_visibility_from_f133 as f136  # noqa: E402


class F136DeferVisibilityBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f133.OUT / f"{f133.BASE_OUT}.decompressed.bin").read_bytes()
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        cls.start = next(entry.data for entry in entries if entry.name == f133.START_ENTRY)

    def test_patch_defers_only_first_post_hostapd_visibility_gate(self) -> None:
        patched, report = f136.patch_start(self.start)
        text = patched.decode("ascii")
        self.assertIn("OMRADIO5_VISIBILITY_DEFER", text)
        self.assertIn("observe_radio5_visibility_state post-hostapd continue-to-coc", text)
        self.assertIn("require_radio5_visibility_state post-coc", text)
        self.assertIn("OMRADIO5_HR_TIMER_POLICY disabled-in-qdrv-init source=f133", text)
        self.assertIn("post_hostapd_defer", report["applied"])

    def test_patch_is_scoped_to_start_script(self) -> None:
        patched, report = f136.patch_start(self.start)
        self.assertGreater(len(patched), len(self.start))
        self.assertEqual(report["entry"], f133.START_ENTRY)
        self.assertIn("queues, DMA, rates, rings", " ".join(report["fixes"]))


if __name__ == "__main__":
    unittest.main()
