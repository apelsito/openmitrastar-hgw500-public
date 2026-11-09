#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx-ampdu-lab.patch"
APPLY = ROOT / "tools/apply_topaz_linux_510_overlay.sh"
BUILDER = ROOT / "tools/build_realtek_8192ee_incremental.sh"


class RealtekTxAmpduLabTests(unittest.TestCase):
    def test_default_off_explicit_parameter(self) -> None:
        text = PATCH.read_text(encoding="utf-8")
        self.assertIn("static bool hgw500_tx_ampdu_disable;", text)
        self.assertIn("module_param_named(hgw500_tx_ampdu_disable", text)
        self.assertIn("bool, 0444", text)

    def test_gate_is_target_ap_8192ee_and_tx_start_only(self) -> None:
        text = PATCH.read_text(encoding="utf-8")
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', text)
        self.assertIn("rtlpriv->rtlhal.hw_type == HARDWARE_TYPE_RTL8192EE", text)
        self.assertIn("vif->type == NL80211_IFTYPE_AP", text)
        gate = text.split("case IEEE80211_AMPDU_TX_START:", 1)[1]
        gate = gate.split("case IEEE80211_AMPDU_TX_STOP_CONT:", 1)[0]
        self.assertIn("return -EOPNOTSUPP;", gate)
        self.assertIn("rtl_tx_agg_start", gate)
        self.assertNotIn("IEEE80211_AMPDU_RX_START", gate)
        self.assertNotIn("case IEEE80211_AMPDU_RX_START:", text)

    def test_marker_is_rate_limited_and_build_is_pinned(self) -> None:
        patch = PATCH.read_text(encoding="utf-8")
        apply = APPLY.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn("pr_info_ratelimited", patch)
        self.assertIn("OMRTLAMPDU stage=tx-start-rejected", patch)
        self.assertIn("rtlwifi-mitrastar-tx-ampdu-lab.patch", apply)
        self.assertIn("hgw500_tx_ampdu_lab_param", builder)


if __name__ == "__main__":
    unittest.main()
