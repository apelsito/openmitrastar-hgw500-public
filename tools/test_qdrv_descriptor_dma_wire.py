#!/usr/bin/env python3
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TX = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_tx.c"
RX = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c"
WLAN = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.h"
COMM = ROOT / "work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h"
WIRE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_dma_wire.h"
REMOTE = ROOT / "tools/qtn_w3_qdrv_sequential_bringup_remote.sh"


def wire_bus(original_dma: int, size: int) -> int:
    if original_dma >> 32 or size <= 0:
        raise ValueError
    if 0x80000000 <= original_dma < 0x88000000:
        wire = original_dma - 0x80000000
    else:
        wire = 0
    if wire == 0 or wire >= 0x08000000 or size > 0x08000000 - wire:
        raise ValueError
    return wire


class DescriptorDmaWireTests(unittest.TestCase):
    def test_common_helper_converts_and_rejects(self):
        self.assertEqual(wire_bus(0x84FB4000, 560), 0x04FB4000)
        for address, size in ((0, 560), (0x08000000, 560),
                              (0x87FFFF00, 0x200), (0x1_84FB4000, 560)):
            with self.assertRaises(ValueError):
                wire_bus(address, size)
        text = WIRE.read_text()
        self.assertIn("qdrv_dma_handle_to_wire", text)
        self.assertIn("virt_to_bus", text)
        self.assertIn("bytes > RUBY_MAX_DRAM_SIZE - wire", text)

    def test_pools_have_real_dma_device(self):
        tx = TX.read_text()
        rx = RX.read_text()
        self.assertNotIn('dma_pool_create("txdesc", NULL', tx)
        self.assertNotIn('dma_pool_create("rxdesc", NULL', rx)
        self.assertIn('dma_pool_create("txdesc", dma_dev', tx)
        self.assertIn('dma_pool_create("rxdesc", dma_dev', rx)
        self.assertIn("qtn_platform_dma_device()", tx)
        self.assertIn("qtn_platform_dma_device()", rx)

    def test_tx_keeps_original_handle_and_publishes_only_wire(self):
        tx = TX.read_text()
        comm = COMM.read_text()
        self.assertIn("uint32_t\t\tdma_handle", comm)
        self.assertIn("ret->dma_handle = (u32)phys", tx)
        self.assertIn("ret->hw_desc.hd_pa = wire_bus", tx)
        self.assertIn("(dma_addr_t)txdesc->dma_handle", tx)
        self.assertIn("(dma_addr_t)tmp->dma_handle", tx)
        self.assertNotRegex(tx, re.compile(r"dma_pool_free\([^;]+hd_pa", re.S))

    def test_rx_parallel_handle_array_survives_wire_abi(self):
        rx = RX.read_text()
        wlan = WLAN.read_text()
        self.assertIn("dma_addr_t *descp_dma", wlan)
        self.assertIn("hfif->descp_dma[i] = original_dma", rx)
        self.assertIn("rd->rd_pa = (struct host_rxdesc *)(unsigned long)wire_bus", rx)
        self.assertIn("hfif->descp_dma[i]", rx)
        self.assertNotRegex(rx, re.compile(r"dma_pool_free\([^;]+rxdesc->rd_pa", re.S))
        self.assertIn("rx_fifo_destroy(hfif)", rx)

    def test_markers_and_runtime_gate_cover_both_paths(self):
        combined = TX.read_text() + RX.read_text()
        for path in ("tx", "rx"):
            self.assertIn(f"OMQDRVDESC stage=pool-create path={path}", combined)
            self.assertIn(f"OMQDRVDESC stage=alloc-pass path={path}", combined)
            self.assertIn(f"OMQDRVDESC stage=pool-create path={path}", REMOTE.read_text())


if __name__ == "__main__":
    unittest.main()
