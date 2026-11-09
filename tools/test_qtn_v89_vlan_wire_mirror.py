#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VLAN = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_vlan.c"
SOC = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.c"
QTN_VLAN = ROOT / "work/sources/Quantenna-GPL/include/qtn/qtn_vlan.h"
CRASH = ROOT / "work/mission-state/q3-muc-rx-crash-window.txt"


class V89VlanWireMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vlan = VLAN.read_text(encoding="utf-8")
        cls.soc = SOC.read_text(encoding="utf-8")
        cls.header = QTN_VLAN.read_text(encoding="utf-8")
        cls.crash = CRASH.read_text(encoding="utf-8")

    def test_crash_is_bound_to_vdev_bus_offset(self) -> None:
        self.assertIn("800215ac", self.crash)
        self.assertIn("800215ca", self.crash)
        self.assertIn("ld\tr8,[r11, 0xb4]", self.crash)

    def test_muc_tables_live_in_persistent_coherent_memory(self) -> None:
        for token in (
            "om_vdev_tbl_muc = dma_alloc_coherent",
            "om_vport_tbl_muc = dma_alloc_coherent",
            "om_vlan_info_muc = dma_alloc_coherent",
            "qdrv_dma_handle_to_wire(om_vdev_tbl_dma",
            "qdrv_dma_handle_to_wire(om_vport_tbl_dma",
            "qdrv_dma_handle_to_wire(om_vlan_info_dma",
            "OMVLAN stage=wire-shadow-ready",
        ):
            self.assertIn(token, self.vlan)

    def test_module_lifetime_owns_wire_tables(self) -> None:
        init = self.vlan[self.vlan.index("static int __init switch_vlan_module_init"):]
        self.assertLess(init.index("om_vlan_wire_init()"), init.index("return 0;"))
        exit_path = self.vlan[self.vlan.index("static void __exit switch_vlan_module_exit"):]
        self.assertIn("om_vlan_wire_exit();", exit_path)

    def test_updates_publish_under_existing_lock_and_barrier(self) -> None:
        alloc = self.vlan[self.vlan.index("struct qtn_vlan_dev *switch_alloc_vlan_dev"):]
        self.assertLess(alloc.index("spin_lock_bh(&lock)"), alloc.index("WRITE_ONCE(om_vdev_tbl_muc[idx]"))
        self.assertLess(alloc.index("WRITE_ONCE(om_vdev_tbl_muc[idx]"), alloc.index("dma_wmb()"))
        self.assertIn("WRITE_ONCE(om_vport_tbl_muc[port], vdev_wire)", alloc)
        self.assertIn("om_vlan_info_sync();", self.vlan)

    def test_shared_params_publish_wire_helpers_not_module_bss(self) -> None:
        start = self.soc.rindex("soc_shared_params->vdev_lhost")
        region = self.soc[start:self.soc.index("#if defined(QBMPS_ENABLE)", start)]
        self.assertIn("switch_vlan_vdev_table_bus()", region)
        self.assertIn("switch_vlan_vport_table_bus()", region)
        self.assertIn("switch_vlan_info_bus()", region)
        self.assertNotIn("virt_to_bus(vdev_tbl_bus)", region)
        self.assertNotIn("virt_to_bus(vport_tbl_bus)", region)
        self.assertNotIn("virt_to_bus(&qtn_vlan_info)", region)
        for prototype in (
            "switch_vlan_vdev_table_bus(void)",
            "switch_vlan_vport_table_bus(void)",
            "switch_vlan_info_bus(void)",
        ):
            self.assertIn(prototype, self.header)


if __name__ == "__main__":
    unittest.main(verbosity=2)
