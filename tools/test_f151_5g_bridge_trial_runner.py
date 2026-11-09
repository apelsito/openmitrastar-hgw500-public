#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class F151BridgeTrialRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (ROOT / "tools/run_f151_5g_bridge_trial.py").read_text(encoding="utf-8")

    def test_requires_explicit_runtime_ack_and_never_flashes(self) -> None:
        self.assertIn("OPENMITRASTAR_F151_5G_BRIDGE_TRIAL", self.text)
        self.assertIn('"flash": False', self.text)
        for forbidden in ("flash_erase", "nandwrite", "mtd_debug", "fw_setenv"):
            self.assertNotIn(forbidden, self.text)

    def test_requires_full_bridge_product_evidence(self) -> None:
        self.assertIn("evaluate_qtn_5g_windows_oracle", self.text)
        self.assertIn('isolated_l3=False', self.text)
        self.assertIn('"--require-client-traffic"', self.text)
        self.assertIn("radio5g-bridge-trial/hostapd.log", self.text)
        self.assertIn("install_temporary_secure_profile", self.text)
        self.assertIn("read_auc_stats", self.text)
        self.assertIn('parser.add_argument("--disable-tx-ba"', self.text)
        self.assertIn('apply_action = "apply-txba-off"', self.text)
        self.assertIn("--transfer-mib", self.text)
        self.assertIn("--disable-uapsd", self.text)
        self.assertIn("collect_router_evidence", self.text)

    def test_always_attempts_isolated_restore(self) -> None:
        self.assertIn("finally:", self.text)
        self.assertIn("restore_isolated(args.router_host)", self.text)
        self.assertIn("remove_temporary_secure_profile", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
