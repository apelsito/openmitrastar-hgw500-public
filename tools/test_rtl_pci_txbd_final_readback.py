#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"
OEM = ROOT / (
    "work/sources/rtl8198c-rtk-ref/rtk_openwrt_sdk/target/linux/realtek/"
    "files/drivers/net/wireless/rtl8192cd/WlanHAL/RTL88XX/Hal88XXTxDesc.c"
)


def test_final_readback_is_target_gated_and_be_only() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    helper = text[
        text.index("static void rtl_pci_hgw500_txbd_final_readback") :
        text.index("static bool rtl_pci_txbd_queue_compact")
    ]
    assert "hgw500_txbd_final_readback" in helper
    assert "hw_queue != BE_QUEUE" in helper
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in helper
    assert "HARDWARE_TYPE_RTL8192EE" in helper
    assert "dma_wmb();" in helper
    assert "READ_ONCE(((__le32 *)txbd)[0])" in helper
    assert "GENMASK(30, 16)" in helper


def test_readback_occurs_after_fill_and_before_publish() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    tx = text[text.index("static int rtl_pci_tx(") : text.index("static void rtl_pci_flush(")]
    fill = tx.index("rtlpriv->cfg->ops->fill_tx_desc")
    readback = tx.index("rtl_pci_hgw500_txbd_final_readback")
    queue = tx.index("__skb_queue_tail")
    publish = tx.index("rtlpriv->cfg->ops->set_desc")
    assert fill < readback < queue < publish


def test_oem_contract_reads_psblen_before_host_index_mmio() -> None:
    text = OEM.read_text(encoding="utf-8", errors="replace")
    sync = text[
        text.index("SyncSWTXBDHostIdxToHW88XX") :
        text.index("//Note: This function can't be used by Beacon")
    ]
    assert "Avoid that IO operation is completed before Packet is put into DRAM" in sync
    assert "TxPktFinalIO88XX_CHECK" in sync
    assert "HAL_RTL_W16(cur_q->reg_rwptr_idx, cur_q->host_idx)" in sync
    assert sync.index("TxPktFinalIO88XX_CHECK") < sync.index("HAL_RTL_W16")

