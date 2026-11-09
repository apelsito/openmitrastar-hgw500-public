#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
HEADER_PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx2-pci-header.patch"
MODE_PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx2-pci-mode.patch"
HW_WIDTH_PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx6-global-txbd-width.patch"
WIDTH_OVERRIDE_PATCH = ROOT / "work/kernel-port/linux-5.10/rtl8192ee-mitrastar-tx26-pbp-width-override.patch"
OVERLAY = ROOT / "tools/apply_topaz_linux_510_overlay.sh"
OEM_HAL_CFG = ROOT / (
    "work/sources/rtl8198c-rtk-ref/rtk_openwrt_sdk/target/linux/realtek/files/"
    "drivers/net/wireless/rtl8192cd/WlanHAL/HalCfg.h"
)
OEM_HAL_GEN = ROOT / (
    "work/sources/rtl8198c-rtk-ref/rtk_openwrt_sdk/target/linux/realtek/files/"
    "drivers/net/wireless/rtl8192cd/WlanHAL/RTL88XX/Hal88XXGen.c"
)


class Tx2SourceTests(unittest.TestCase):
    def test_compact_layout_is_opt_in_and_target_gated(self) -> None:
        pci = PCI.read_text(encoding="utf-8")
        self.assertIn("static bool hgw500_txbd_compact32;", pci)
        self.assertIn("module_param_named(hgw500_txbd_compact32", pci)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', pci)
        self.assertIn("HARDWARE_TYPE_RTL8192EE", pci)
        self.assertIn("!rtlpriv->cfg->mod_params->dma64", pci)
        self.assertIn("rtl_pci_txbd_queue_compact(rtlpriv, rtlpci, prio) ?", pci)
        self.assertIn("prio == BE_QUEUE && hgw500_txbd_be_legacy64", pci)
        self.assertNotIn("rtlpci->txbd_compact32 && prio <= VO_QUEUE", pci)

    def test_dma_allocation_and_indexing_use_runtime_stride(self) -> None:
        pci = PCI.read_text(encoding="utf-8")
        self.assertIn("buffer_desc_stride * entries", pci)
        self.assertIn("rtl_pci_txbd_entry(ring, idx)", pci)
        self.assertIn("idx * ring->buffer_desc_stride", pci)
        self.assertIn("_rtl_pci_tx_buffer_addr(hw, ring, entry)", pci)
        self.assertNotIn("&ring->buffer_desc[idx]", pci)

    def test_compact_layout_matches_oem_words(self) -> None:
        trx = TRX.read_text(encoding="utf-8")
        self.assertIn("memset(tx_bd_desc, 0, 32);", trx)
        self.assertIn("tx_bd_desc[1] = cpu_to_le32((u32)desc_dma_addr);", trx)
        self.assertIn("tx_bd_desc[2] = cpu_to_le32(pkt_len);", trx)
        self.assertIn("tx_bd_desc[3] = cpu_to_le32((u32)addr);", trx)
        self.assertIn("buffer_desc_stride == 32", trx)

    def test_compact_layout_clears_recycled_tx_descriptor(self) -> None:
        trx = TRX.read_text(encoding="utf-8")
        compact_start = trx.index("if (compact32) {")
        compact_end = trx.index("\t\treturn;", compact_start)
        compact = trx[compact_start:compact_end]
        clear = compact.index("clear_pci_tx_desc_content(desc, TX_DESC_SIZE);")
        pkt_size = compact.index("set_tx_desc_pkt_size(desc, (u16)pkt_len);")
        buffer_size = compact.index("set_tx_desc_tx_buffer_size(desc, (u16)pkt_len);")
        self.assertLess(clear, pkt_size)
        self.assertLess(clear, buffer_size)

    def test_runtime_layout_selector_matches_current_hybrid_experiment(self) -> None:
        pci = PCI.read_text(encoding="utf-8")
        self.assertIn("rtl_pci_txbd_queue_compact(rtlpriv, rtlpci, prio) ?", pci)
        self.assertIn("32 : sizeof(*buffer_desc)", pci)
        self.assertNotIn("prio <= VO_QUEUE ?", pci)
        self.assertIn("prio == BE_QUEUE && hgw500_txbd_be_legacy64", pci)
        self.assertIn("OMRTLTX9 stage=txbd-ring q=%u stride=%u compact=%u", pci)
        self.assertIn("Use the OEM global 32-byte RTL8192EE TXBD width", pci)

        width_override = WIDTH_OVERRIDE_PATCH.read_text(encoding="utf-8")
        self.assertIn("hgw500_force_txbd64_width", width_override)
        self.assertIn("wordtmp |= BIT(15);", width_override)
        self.assertIn("rtl_write_word(rtlpriv, REG_RX_RXBD_NUM, wordtmp);", width_override)
        self.assertIn("force64=%u", width_override)

        overlay = OVERLAY.read_text(encoding="utf-8")
        self.assertIn("rtlwifi-mitrastar-tx6-global-txbd-width.patch", overlay)

    def test_oem_width_contract_and_explicit_64bit_override_are_documented(self) -> None:
        hal_cfg = OEM_HAL_CFG.read_text(encoding="utf-8", errors="replace")
        hal_gen = OEM_HAL_GEN.read_text(encoding="utf-8", errors="replace")
        hw_patch = HW_WIDTH_PATCH.read_text(encoding="utf-8")
        width_override = WIDTH_OVERRIDE_PATCH.read_text(encoding="utf-8")

        self.assertIn("#define TXBD_SEG_32_64_SEL      0", hal_cfg)
        self.assertIn("RXBDReg & ~BIT_SYS_32_64", hal_gen)
        self.assertIn("TXBD_SEG_32_64_SEL << 15", hal_gen)
        self.assertIn("wordtmp = RX_DESC_NUM_92E", hw_patch)
        self.assertIn("if (!rtlpci->txbd_compact32)", hw_patch)
        self.assertIn("wordtmp |= BIT(15);", hw_patch)
        self.assertIn("hgw500_force_txbd64_width", width_override)
        self.assertIn("force64=%u", width_override)
        self.assertIn(
            "rtl_pci_txbd_queue_compact(rtlpriv, rtlpci, prio) ?",
            PCI.read_text(encoding="utf-8"),
        )

    def test_tx_queue_log_carries_explicit_hardware_queue(self) -> None:
        pci = PCI.read_text(encoding="utf-8")
        self.assertIn(
            "OMRTL stage=pci-tx-queued id=%u q=%u queue_len=%u",
            pci,
        )
        queued_log = pci.index("OMRTL stage=pci-tx-queued")
        queued_block = pci[queued_log:queued_log + 220]
        self.assertIn("trace_id, hw_queue, skb_queue_len(&ring->queue)", queued_block)

    def test_txbd_trace_uses_actual_ring_stride(self) -> None:
        pci = PCI.read_text(encoding="utf-8")
        trace_log = pci.index("OMRTL stage=pci-tx-bd-filled")
        trace_block_start = pci.rindex("if (txbd) {", 0, trace_log)
        trace_block = pci[trace_block_start:trace_log + 1200]
        self.assertIn("ring->buffer_desc_stride == 32", trace_block)
        self.assertNotIn("if (rtlpci->txbd_compact32)", trace_block)

    def test_reclaim_semantics_are_not_weakened(self) -> None:
        trx = TRX.read_text(encoding="utf-8")
        self.assertIn("index == HW RP is not", trx)
        self.assertIn("if (index > write_point && index < read_point)", trx)
        self.assertNotIn("desc_own == 0", trx)
        self.assertNotIn("bd_own == 0", trx)

    def test_header_contract_adds_stride_and_mode(self) -> None:
        patch = HEADER_PATCH.read_text(encoding="utf-8")
        mode = MODE_PATCH.read_text(encoding="utf-8")
        self.assertIn("u16 buffer_desc_stride;", patch)
        self.assertIn("bool txbd_compact32;", mode)
        self.assertIn("rtl_pci_txbd_entry", patch)


if __name__ == "__main__":
    unittest.main()
