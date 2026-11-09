#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QDRV_SHA = "600a6f98bb3151cf80755bd5132b8bc9a7460b86146557d57ba8c97568d5a581"
WLAN_SHA = "a750b273c0570c2ccfe0fce3f28a311d2e8e3b9f7d7ef9f7cd9ed48046065233"
CANDIDATE_SHA = "9eb679bb6c4fb9cfb4a5cacf8bbcff2a2ce6c9c063d29f9f4d54b3d6262ac800"


class F148OpsContractTests(unittest.TestCase):
    def test_postflash_gate_requires_matched_pair(self) -> None:
        text = (ROOT / "tools/post_flash_f13x_radio_gate.ps1").read_text(encoding="utf-8")
        self.assertIn('"F148"', text)
        self.assertIn(QDRV_SHA, text)
        self.assertIn(WLAN_SHA, text)
        self.assertIn("PASS_F148_5G_SUBPORT_MAP_PAIR_READY", text)
        self.assertIn("$qdrvF148 -and $wlanF148", text)

    def test_aelita_gate_requires_matched_pair(self) -> None:
        text = (ROOT / "tools/run_f142_5g_aelita_certification.py").read_text(encoding="utf-8")
        self.assertIn('"F148": "OPENMITRASTAR_F148_5G_AELITA_CERTIFICATION"', text)
        self.assertIn(QDRV_SHA, text)
        self.assertIn(WLAN_SHA, text)
        self.assertIn("__WLAN_SHA__", text)
        self.assertNotIn(
            'wlan.ko | awk \'{print $1}\')\" = 97fac710018a2bbd59dca616537171d04da1ece771c4c22439710152e6b4fe29',
            text,
        )

    def test_flash_wrapper_is_pinned_to_mtd4_candidate(self) -> None:
        text = (ROOT / "tools/arm_f148_5g_subport_map_pair_flash.ps1").read_text(encoding="utf-8")
        self.assertIn(CANDIDATE_SHA, text)
        self.assertIn('$CurrentLiveCrc32 = "7cac8eab"', text)
        self.assertIn("OM_Q3_FLASH_EXPECTED_SHA256", text)
        self.assertIn("autoboot_atgu_flash.ps1", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
