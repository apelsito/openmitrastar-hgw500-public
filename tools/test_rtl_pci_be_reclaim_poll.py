#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"


def test_reclaim_poll_is_opt_in_and_target_gated() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    assert "static bool hgw500_tx_reclaim_poll;" in text
    assert "module_param_named(hgw500_tx_reclaim_poll" in text
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "HARDWARE_TYPE_RTL8192EE" in text
    assert "hgw500_tx_queue_guard &&" in text
    assert "hgw500_be_queue_guard_stopped" in text


def test_stop_arms_existing_delayed_work() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    tx = text[text.index("static int rtl_pci_tx(") : text.index("static void rtl_pci_flush(")]
    assert "ieee80211_stop_queue" in tx
    assert "schedule_delayed_work(" in tx
    assert "&rtlpriv->works.irq_rx_work, 1" in tx
    assert "OMRTLQGUARD stage=reclaim-arm" in tx


def test_poll_reuses_normal_hardware_rp_close_predicate() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    work = text[text.index("static void _rtl_pci_rx_work") : text.index("static irqreturn_t _rtl_pci_interrupt")]
    assert "_rtl_pci_tx_isr(hw, BE_QUEUE);" in work
    assert "OMRTLQGUARD stage=reclaim-poll" in work
    assert "guard_requeued = rtl_pci_hgw500_be_reclaim_rearm" in work
    assert "requeued = rx_requeued || guard_requeued;" in work
    assert "if (!rx_requeued && active)" in work
    assert "ieee80211_tx_status_irqsafe" not in work
    assert "dev_kfree_skb" not in work


def test_poll_does_not_change_descriptor_ownership() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    work = text[text.index("static void _rtl_pci_rx_work") : text.index("static irqreturn_t _rtl_pci_interrupt")]
    forbidden = (
        "dma_unmap_single",
        "__skb_dequeue",
        "set_tx_buff_desc_own",
        "ring->idx =",
        "ring->cur_tx_rp =",
        "ring->cur_tx_wp =",
    )
    for needle in forbidden:
        assert needle not in work
