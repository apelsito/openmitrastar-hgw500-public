#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_SHA = "4e5ff1eaeca084cebc0f55ff853daf6709e6f6a951ba8ede53cfe218947bd48c"


class F150OpsContractTests(unittest.TestCase):
    def test_gate_requires_autostart_and_module_pair(self) -> None:
        text = (ROOT / "tools/post_flash_f13x_radio_gate.ps1").read_text(encoding="utf-8")
        self.assertIn('"F150"', text)
        self.assertIn("PASS_F150_5G_AUTOSTART_READY_READONLY", text)
        self.assertIn("$radio5AutostartEnabled", text)
        self.assertIn("$qdrvF148 -and $wlanF148 -and $startF149", text)
        self.assertIn('$Profile -eq "F150" -and -not $RunRadio5Start -and $ready5', text)

    def test_certification_supports_f150_pair(self) -> None:
        text = (ROOT / "tools/run_f142_5g_aelita_certification.py").read_text(encoding="utf-8")
        self.assertIn('"F150": "OPENMITRASTAR_F150_5G_AELITA_CERTIFICATION"', text)
        self.assertIn('PROFILE_WLAN_SHA["F150"]', text)

    def test_flash_wrapper_pins_f149_live_crc_and_f150_hash(self) -> None:
        text = (ROOT / "tools/arm_f150_5g_autostart_enable_flash.ps1").read_text(encoding="utf-8")
        self.assertIn(CANDIDATE_SHA, text)
        self.assertIn('$CurrentLiveCrc32 = "a9df1486"', text)
        self.assertIn("autoboot_atgu_flash.ps1", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
