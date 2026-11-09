#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VLAN = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_vlan.c"
SOC = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.c"


class VlanWireShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vlan = VLAN.read_text(encoding="utf-8")
        cls.soc = SOC.read_text(encoding="utf-8")

    def test_target_gets_coherent_low_bus_shadows(self) -> None:
        for token in (
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            "dma_alloc_coherent",
            "qdrv_dma_handle_to_wire(om_vdev_tbl_dma",
            "qdrv_dma_handle_to_wire(om_vport_tbl_dma",
            "qdrv_dma_handle_to_wire(om_vlan_info_dma",
            "OMVLAN stage=wire-shadow-ready",
        ):
            self.assertIn(token, self.vlan)

    def test_entries_use_wire_addresses_and_original_dma_is_retained(self) -> None:
        self.assertIn("WRITE_ONCE(om_vdev_tbl_muc[idx], vdev_wire)", self.vlan)
        self.assertIn("WRITE_ONCE(om_vport_tbl_muc[port], vdev_wire)", self.vlan)
        self.assertIn("om_vdev_dma[idx] = bus_addr", self.vlan)
        self.assertIn("om_vintf_dma[idx] = bus_addr2", self.vlan)
        self.assertIn("dma_free_coherent(dma_dev, sizeof(struct qtn_vlan_dev), vdev, vdev_dma)", self.vlan)

    def test_shared_publisher_uses_shadow_accessors(self) -> None:
        self.assertIn("soc_shared_params->vdev_bus = switch_vlan_vdev_table_bus()", self.soc)
        self.assertIn("soc_shared_params->vport_bus = switch_vlan_vport_table_bus()", self.soc)
        self.assertIn("soc_shared_params->vlan_info = switch_vlan_info_bus()", self.soc)
        self.assertIn("OMQDRVSHM stage=vlan-wire", self.soc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
