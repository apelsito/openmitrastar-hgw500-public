from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f136_5g_defer_post_hostapd_visibility_from_f133 as f136  # noqa: E402
import build_f137_5g_post_hostapd_rearm_from_f136 as f137  # noqa: E402


class F137PostHostapdRearmBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = (f136.OUT / f"{f136.BASE_OUT}.decompressed.bin").read_bytes()
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        cls.start = next(entry.data for entry in entries if entry.name == f136.START_ENTRY)

    def test_patch_rearms_wifi0_and_observes_post_coc(self) -> None:
        patched, report = f137.patch_start(self.start)
        text = patched.decode("ascii")
        self.assertIn("OMRADIO5_VISIBILITY_DEFER", text)
        self.assertIn("OMRADIO5_POST_HOSTAPD_REARM", text)
        self.assertIn("OMRADIO5_POST_COC_REARM", text)
        self.assertIn("OMRADIO5_CARRIER_PENDING_OBSERVE", text)
        self.assertIn("observe_radio5_visibility_state post-hostapd continue-to-coc", text)
        self.assertIn("observe_radio5_visibility_state post-coc continue-carrier-probe", text)
        self.assertNotIn("require_radio5_visibility_state post-coc", text)
        self.assertIn("start_assoc_window_guard", text)
        self.assertIn("OMRADIO5_HR_TIMER_POLICY disabled-in-qdrv-init source=f133", text)
        self.assertIn("post_hostapd_rearm", report["applied"])
        self.assertIn("post_coc_observe", report["applied"])

    def test_patch_is_scoped_to_start_script(self) -> None:
        patched, report = f137.patch_start(self.start)
        self.assertGreater(len(patched), len(self.start))
        self.assertEqual(report["entry"], f136.START_ENTRY)
        self.assertIn("queues, DMA, rates, rings", " ".join(report["fixes"]))


if __name__ == "__main__":
    unittest.main()
