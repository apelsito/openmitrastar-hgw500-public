#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
HEADER = ROOT / "work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
BUILDER = ROOT / "tools/build_q3_persistent_composite.sh"


class DualPhyAutonegTests(unittest.TestCase):
    def test_feature_is_exact_target_and_explicit_dt_gated(self):
        source = DRIVER.read_text(encoding="utf-8")
        gate = source[source.index("emac->phy_autoneg ="):source.index("if (emac->phy_autoneg) {", source.index("emac->phy_autoneg ="))]
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', gate)
        self.assertIn('of_device_is_compatible(dev->of_node, "qtn,topaz-emac")', gate)
        self.assertIn('"qtn,ram-rescue-phy-autoneg"', gate)

    def test_dts_binds_both_qhs860_mac_phy_irq_pairs(self):
        dts = DTS.read_text(encoding="utf-8")
        for token in (
            'reg-names = "emac1", "emac0";',
            'interrupts = <20>, <19>;',
            'interrupt-names = "emac1", "emac0";',
            'qtn,ram-rescue-phy-autoneg;',
            'qtn,phy-addresses = <3 1>;',
            'qtn,mac-ids = <1 0>;',
        ):
            self.assertIn(token, dts)

    def test_driver_restarts_autoneg_and_chooses_linked_port(self):
        source = DRIVER.read_text(encoding="utf-8")
        select = source[source.index("static int qtn_emac_select_rescue_port"):source.index("static void qtn_emac_program_gmii_clock")]
        self.assertIn("BMCR_ANENABLE | BMCR_ANRESTART", select)
        self.assertIn("QTN_TOPAZ_EMAC_AUTONEG_TIMEOUT_MS", select)
        self.assertIn("BMSR_LSTATUS", source)
        self.assertIn("BMSR_ANEGCOMPLETE", source)
        self.assertIn("emac->regs = emac->ports[i].regs", select)
        self.assertIn("emac->irq = emac->ports[i].irq", select)

    def test_mac_and_soc_clock_follow_negotiated_speed(self):
        source = DRIVER.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn("qtn_emac_program_gmii_clock(emac);", source)
        self.assertIn("QTN_TOPAZ_GMII0_CLOCK_SHIFT", header)
        self.assertIn("QTN_TOPAZ_GMII1_CLOCK_SHIFT", header)
        self.assertIn("QTN_EMAC_MAC_FULL_DUPLEX", source)

    def test_q3_builder_can_pin_driver_and_header_sources(self):
        source = BUILDER.read_text(encoding="utf-8")
        for token in (
            "OM_Q3_EMAC_DRIVER_PATH",
            "OM_Q3_EXPECTED_EMAC_DRIVER_SHA256",
            "OM_Q3_EMAC_HEADER_PATH",
            "OM_Q3_EXPECTED_EMAC_HEADER_SHA256",
            'ram_only_overrides["emac_dual_phy_autoneg"]',
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
