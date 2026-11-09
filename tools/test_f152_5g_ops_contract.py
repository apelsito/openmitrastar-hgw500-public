#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WLAN_SHA = "f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f"
CANDIDATE_SHA = "6cd3496cc2d8148396f7a143516eceb65b6480c544f9f770d7ad616292466612"


class F152OpsContractTests(unittest.TestCase):
    def test_postflash_and_client_gates_pin_f152(self) -> None:
        post = (ROOT / "tools/post_flash_f13x_radio_gate.ps1").read_text(encoding="utf-8")
        cert = (ROOT / "tools/run_f142_5g_aelita_certification.py").read_text(encoding="utf-8")
        self.assertIn('"F152"', post)
        self.assertIn(WLAN_SHA, post)
        self.assertIn('"F152": "OPENMITRASTAR_F152_5G_AELITA_CERTIFICATION"', cert)
        self.assertIn(WLAN_SHA, cert)

    def test_bridge_trial_can_pin_diagnostic_wlan_and_capture_trace(self) -> None:
        text = (ROOT / "tools/run_f151_5g_bridge_trial.py").read_text(encoding="utf-8")
        self.assertIn("--expected-wlan-sha", text)
        self.assertIn("OMQTNINACT", text)

    def test_flash_wrapper_is_pinned_to_f151_slot(self) -> None:
        text = (ROOT / "tools/arm_f152_5g_inactivity_trace_flash.ps1").read_text(encoding="utf-8")
        self.assertIn(CANDIDATE_SHA, text)
        self.assertIn('$CurrentLiveCrc32 = "4046c935"', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
