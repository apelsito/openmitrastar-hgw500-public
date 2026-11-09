#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"


def test_f106_reclaim_rearm_is_existing_guard_gated() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    helper = text[text.index("static bool rtl_pci_hgw500_be_reclaim_rearm") : text.index("static void _rtl_pci_topaz_tx_complete")]
    for needle in (
        "hgw500_tx_reclaim_poll",
        "hgw500_tx_queue_guard",
        "hgw500_be_queue_guard_stopped",
        'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
        "HARDWARE_TYPE_RTL8192EE",
        "driver_is_goingto_unload",
        "irq_line_disabled",
        "is_hal_stop",
    ):
        assert needle in helper


def test_f106_reclaim_rearm_never_completes_tx_synchronously() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    helper = text[text.index("static bool rtl_pci_hgw500_be_reclaim_rearm") : text.index("static void _rtl_pci_topaz_tx_complete")]
    assert "mod_delayed_work(system_wq, &rtlpriv->works.irq_rx_work, 1)" in helper
    assert "OMRTLQGUARD stage=reclaim-rearm" in helper
    assert "_rtl_pci_tx_isr" not in helper
    for forbidden in (
        "dma_unmap_single",
        "__skb_dequeue",
        "ieee80211_tx_status_irqsafe",
        "set_desc",
        "set_tx_buff_desc_own",
        "ring->idx =",
        "ring->cur_tx_rp =",
        "ring->cur_tx_wp =",
    ):
        assert forbidden not in helper


def test_f106_tx_stop_rearms_when_delayed_work_is_already_pending() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    tx = text[text.index("static int rtl_pci_tx(") : text.index("static void rtl_pci_flush(")]
    assert "bool queued = schedule_delayed_work(" in tx
    assert "OMRTLQGUARD stage=reclaim-arm" in tx
    assert "if (!queued)" in tx
    assert 'rtl_pci_hgw500_be_reclaim_rearm(hw,\n\t\t\t\t\t\t\t\t"tx-arm-busy");' in tx


def test_f106_rx_work_uses_rearm_for_guard_poll_loop() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    work = text[text.index("static void _rtl_pci_rx_work") : text.index("static irqreturn_t _rtl_pci_interrupt")]
    assert "_rtl_pci_tx_isr(hw, BE_QUEUE);" in work
    assert "rtl_pci_hgw500_be_reclaim_rearm(hw," in work
    assert '"rx-work"' in work
