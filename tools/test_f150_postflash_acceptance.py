#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class F150PostflashAcceptanceTests(unittest.TestCase):
    def test_waits_for_autostart_without_starting_radio(self) -> None:
        text = (ROOT / "tools/run_f150_postflash_acceptance.ps1").read_text(encoding="utf-8")
        self.assertIn("/run/openmitrastar/radio5g/state", text)
        self.assertIn("PASS_F150_5G_AUTOSTART_READY_READONLY", text)
        self.assertNotIn("-RunRadio5Start", text)
        self.assertNotIn("/usr/sbin/om-radio5-start", text)

    def test_runs_f150_aelita_certification_and_requires_ack(self) -> None:
        text = (ROOT / "tools/run_f150_postflash_acceptance.ps1").read_text(encoding="utf-8")
        self.assertIn("OPENMITRASTAR_F150_POSTFLASH_ACCEPTANCE", text)
        self.assertIn("OPENMITRASTAR_F150_5G_AELITA_CERTIFICATION", text)
        self.assertIn("--profile F150", text)
        self.assertIn("--expected-txpower-dbm 21", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
