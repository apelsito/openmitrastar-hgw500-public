from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi"


class RealtekV4PerfPatchTests(unittest.TestCase):
    def test_92ee_rate_descriptor_matches_ht_layout(self):
        header = (RTL / "rtl8192ee/trx.h").read_text()
        self.assertIn("get_rx_desc_rxmcs", header)
        self.assertIn("GENMASK(5, 0)", header)
        self.assertIn("get_rx_desc_rxht", header)
        self.assertIn("BIT(6)", header)
        self.assertIn("get_rx_desc_faggr", header)
        self.assertIn("BIT(16)", header)

    def test_query_populates_ht_bw_and_ampdu_metadata(self):
        source = (RTL / "rtl8192ee/trx.c").read_text()
        for needle in (
            "status->shortpreamble = (u16)get_rx_desc_splcp(pdesc);",
            "status->isfirst_ampdu",
            "status->rx_is40mhzpacket = (bool)get_rx_desc_bw(pdesc);",
            "status->is_ht = (bool)get_rx_desc_rxht(pdesc);",
            "OMRTL92 stage=rx-rate-decode",
        ):
            self.assertIn(needle, source)

    def test_v3_lockup_fix_and_deferred_tx_completion_survive(self):
        source = (RTL / "pci.c").read_text()
        for needle in (
            "more = processed == RTL_TOPAZ_RX_WORK_BUDGET",
            "intb-only vector is real work",
            "topaz_deferred_inta |= intvec.inta",
            '_rtl_pci_topaz_tx_complete(hw, &deferred, "rx-work")',
            "OMRTL stage=tx-complete",
        ):
            self.assertIn(needle, source)
        self.assertNotIn("_rtl_pci_topaz_rx_pending", source)


if __name__ == "__main__":
    unittest.main()
