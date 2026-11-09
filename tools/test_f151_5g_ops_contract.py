#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_SHA = "3d1d5d287f6f6736e1b1099ee681333aa5a41775e2ceefbd57e10eb3bce3e2c9"


class F151OpsContractTests(unittest.TestCase):
    def test_gate_requires_secure_runtime(self) -> None:
        text = (ROOT / "tools/post_flash_f13x_radio_gate.ps1").read_text(encoding="utf-8")
        self.assertIn('"F151"', text)
        self.assertIn("PASS_F151_5G_WPA2_READY_READONLY", text)
        self.assertIn("$radio5OpenLabDisabled", text)
        self.assertIn("$wpa2Ready", text)

    def test_flash_wrapper_is_pinned(self) -> None:
        text = (ROOT / "tools/arm_f151_5g_wpa2_secure_flash.ps1").read_text(encoding="utf-8")
        self.assertIn(CANDIDATE_SHA, text)
        self.assertIn('$CurrentLiveCrc32 = "de411a32"', text)

    def test_secure_acceptance_never_invokes_radio_start(self) -> None:
        text = (ROOT / "tools/run_f151_secure_postflash_acceptance.ps1").read_text(encoding="utf-8")
        self.assertNotIn("-RunRadio5Start", text)
        self.assertNotIn("/usr/sbin/om-radio5-start", text)
        self.assertIn("--profile F151", text)
        self.assertIn("WPA2-PSK-CCMP", text)

    def test_python_gate_uses_temporary_secure_profile(self) -> None:
        text = (ROOT / "tools/run_f142_5g_aelita_certification.py").read_text(encoding="utf-8")
        self.assertIn('PROFILE_SECURITY["F151"] = "wpa2"', text)
        self.assertIn('PROFILE_SSID["F151"] = "MOVISTAR_PLUS_55CB"', text)
        self.assertIn("install_temporary_secure_profile", text)
        self.assertIn("remove_temporary_secure_profile", text)
        self.assertNotIn("keyMaterial>{psk}</keyMaterial>", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
