#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-honest-tx-ack-lab.patch"
APPLY = ROOT / "tools/apply_topaz_linux_510_overlay.sh"
BUILDER = ROOT / "tools/build_realtek_8192ee_incremental.sh"


class RealtekHonestTxAckLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PATCH.read_text(encoding="utf-8")

    def test_parameter_is_explicit_and_default_off(self) -> None:
        self.assertIn("bool rtl_hgw500_honest_tx_ack;", self.text)
        self.assertIn("module_param_named(hgw500_honest_tx_ack", self.text)
        self.assertIn("bool, 0444", self.text)

    def test_parameter_cross_module_symbol_is_explicit(self) -> None:
        self.assertIn("EXPORT_SYMBOL_GPL(rtl_hgw500_honest_tx_ack)", self.text)
        self.assertIn("extern bool rtl_hgw500_honest_tx_ack", self.text)

    def test_policy_is_target_and_chip_gated(self) -> None:
        self.assertGreaterEqual(
            self.text.count('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")'),
            2,
        )
        self.assertGreaterEqual(
            self.text.count("HARDWARE_TYPE_RTL8192EE"),
            2,
        )

    def test_reports_ack_flag_survives_default_path(self) -> None:
        self.assertIn("if (rtl_hgw500_honest_tx_ack", self.text)
        self.assertIn("ieee80211_hw_set(hw, REPORTS_TX_ACK_STATUS);", self.text)
        self.assertIn("OMRTLACK stage=policy-active", self.text)

    def test_completion_does_not_inject_ack_when_active(self) -> None:
        self.assertIn("if (!honest_ack)", self.text)
        self.assertIn("info->flags |= IEEE80211_TX_STAT_ACK;", self.text)
        honest = self.text.split("if (!honest_ack)", 1)[1]
        honest = honest.split("ieee80211_tx_status_irqsafe", 1)[0]
        self.assertNotIn("TX_STAT_ACK;", honest.split("} else {", 1)[1])

    def test_markers_are_bounded(self) -> None:
        self.assertIn("pr_info_once", self.text)
        self.assertIn("trace_id <= 8 || is_power_of_2(trace_id)", self.text)
        self.assertIn("completion-no-fabricated-ack", self.text)

    def test_ampdu_policy_is_not_modified(self) -> None:
        self.assertNotIn("IEEE80211_AMPDU_TX_START", self.text)
        self.assertNotIn("rtl_tx_agg_start", self.text)
        self.assertIn("ampdu=unchanged", self.text)

    def test_build_pipeline_pins_patch_and_gate(self) -> None:
        apply = APPLY.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn("rtlwifi-mitrastar-honest-tx-ack-lab.patch", apply)
        self.assertIn("hgw500_honest_tx_ack_lab_param", builder)
        self.assertIn("ack_policy_unchanged", builder)


if __name__ == "__main__":
    unittest.main()
