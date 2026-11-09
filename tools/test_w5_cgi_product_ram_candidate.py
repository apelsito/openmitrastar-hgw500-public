#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_w5_cgi_product_ram_candidate.ps1"
BUILD = ROOT / "work/mission-state/w5-cgi-product-ram-candidate/build"


class W5CgiProductRamTests(unittest.TestCase):
    def test_package_contract(self):
        package = json.loads((BUILD / "packaging-manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(package["candidate_eligible"])
        self.assertEqual(
            package["classification"],
            "RAM-ONLY-PRODUCT-CGI-WATCHDOG-CANDIDATE-NO-FLASH",
        )
        self.assertTrue(package["bootbase_ras"]["accepted"])
        self.assertLess(package["bootbase_ras"]["image_bytes"], package["bootbase_ras"]["slot_bytes"])
        self.assertTrue(package["protected_w3_watchdog"]["unchanged"])
        self.assertTrue(package["separate_tftp_output"]["distinct_from_w3_watchdog"])
        for gate in package["reproducibility"].values():
            self.assertTrue(gate["identical"])
            self.assertEqual(gate["pass_a_sha256"], gate["pass_b_sha256"])

    def test_runner_is_separate_and_dry_by_default(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn('$Filename = "linux510-product-cgi-ram-v1-RAM-ONLY.bin"', text)
        self.assertIn("linux510-product-watchdog-canary-v1-RAM-ONLY.bin", text)
        self.assertIn("W5_CGI_PRODUCT_RAM_BOOT_DRY_RUN_PASS=1", text)
        self.assertNotRegex(text, re.compile(r"\b(?:flash_erase|nandwrite|mtd_debug|ubiformat)\b"))
        syntax = subprocess.run(
            ["pwsh.exe", "-NoProfile", "-Command",
             f"[void][scriptblock]::Create((Get-Content -Raw '{RUNNER}'))"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        dry = subprocess.run(
            ["pwsh.exe", "-NoProfile", "-File", str(RUNNER)],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("W5_CGI_PRODUCT_RAM_BOOT_DRY_RUN_PASS=1", dry.stdout)


if __name__ == "__main__":
    unittest.main()
