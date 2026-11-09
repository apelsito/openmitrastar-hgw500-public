#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "work/mission-state/w4-rootfs-product/scripts/build_product_rootfs.sh"
LOADER = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-radio-modules"
Q3_BUILDER = ROOT / "tools/build_q3_persistent_composite.sh"


class ProductRealtekModuleOptionsTests(unittest.TestCase):
    def test_product_busybox_preserves_insmod_options(self) -> None:
        text = BUILDER.read_text(encoding="utf-8")
        self.assertIn("--enable FEATURE_CMDLINE_MODULE_OPTIONS", text)
        self.assertIn("CONFIG_FEATURE_CMDLINE_MODULE_OPTIONS=y", text)

    def test_loader_uses_and_verifies_all64_mcs7_profile(self) -> None:
        text = LOADER.read_text(encoding="utf-8")
        self.assertIn(
            "hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0",
            text,
        )
        self.assertIn(
            "msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 "
            "disable_watchdog=0 debug_level=0 hgw500_force_txbd64_width=1",
            text,
        )
        for expectation in (
            "hgw500_txbd_compact32=N",
            "hgw500_txbd_tx5_layout=N",
            "hgw500_txbd_be_legacy64=N",
            "hgw500_tx_queue_guard=N",
            "hgw500_txbd_final_readback=N",
            "hgw500_tx_reclaim_poll=N",
            "msi=N",
            "dma64=N",
            "aspm=0",
            "ips=N",
            "fwlps=N",
            "swenc=Y",
            "disable_watchdog=N",
            "debug_level=0",
            "hgw500_force_txbd64_width=Y",
            "hgw500_tx_dma_wmb=Y",
            "hgw500_tx_close_diag=N",
            "hgw500_tx_page_units=2",
            "hgw500_tx_pbp_256=N",
            "hgw500_txbd_mgmt_split=N",
            "hgw500_force_data_mcs7=Y",
            "hgw500_force_data_mcs15=N",
            "hgw500_force_data_11m=N",
            "hgw500_txbd_be_data_split=Y",
            "hgw500_tx_rate_trace=N",
        ):
            self.assertIn(expectation, text)
        self.assertIn("profile=all64-mcs7-eapol-mgntq-q2", text)
        self.assertIn("eapol_trace=%s eapol_mgnt_queue=%s", text)
        self.assertIn("eapol_param_source=insmod", text)
        self.assertIn("hgw500_eapol_trace=$radio2g_eapol_trace", text)
        self.assertIn("radio2g_eapol_mgnt_queue=1", text)
        self.assertIn("hgw500_eapol_mgnt_queue=$radio2g_eapol_mgnt_queue", text)
        self.assertLess(
            text.index("hgw500_eapol_trace=$radio2g_eapol_trace"),
            text.index('if ! load_module "$module_dir/$module" "$parameters"; then'),
        )
        self.assertIn("OMRADIO_MODULE_PARAMS_PASS", text)
        self.assertIn('refuse "module-param-rtl8192ee-$parameter"', text)
        self.assertIn('"$module_loader" "$path" "$parameters"', text)

    def test_q3_overlays_the_fixed_loader(self) -> None:
        text = Q3_BUILDER.read_text(encoding="utf-8")
        self.assertIn(
            'canonical_radio_modules="${OM_Q3_RADIO_MODULES_PATH:-$canonical_product_rootfs/usr/sbin/om-radio-modules}"',
            text,
        )
        self.assertIn(
            'cp "$canonical_radio_modules" "$stage/usr/sbin/om-radio-modules"',
            text,
        )
        self.assertIn(
            'require_sha "$canonical_radio_modules" "$expected_canonical_radio_modules"',
            text,
        )


if __name__ == "__main__":
    unittest.main()
