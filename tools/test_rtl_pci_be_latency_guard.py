#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"


def test_guard_thresholds_are_configurable_and_safe() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    assert "static unsigned int hgw500_tx_queue_guard_high = 64;" in text
    assert "static unsigned int hgw500_tx_queue_guard_low = 32;" in text
    assert "module_param_named(hgw500_tx_queue_guard_high" in text
    assert "module_param_named(hgw500_tx_queue_guard_low" in text
    assert "clamp_t(unsigned int, hgw500_tx_queue_guard_high, 2," in text
    assert "min_t(unsigned int, hgw500_tx_queue_guard_low, high - 1)" in text


def test_guard_has_explicit_stop_wake_hysteresis() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    assert "hgw500_be_queue_guard_stopped" in text
    assert "!hgw500_be_queue_guard_stopped" in text
    assert "hgw500_be_queue_guard_stopped = true;" in text
    assert "hgw500_be_queue_guard_stopped = false;" in text
    assert "OMRTLQGUARD stage=stop" in text
    assert "OMRTLQGUARD stage=wake" in text


def test_queue_mapping_is_saved_before_tx_status_handoff() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    isr = text[text.index("static void _rtl_pci_tx_isr") : text.index("static void _rtl_pci_topaz_tx_complete")]
    saved = isr.index("queue_mapping = skb_get_queue_mapping(skb);")
    status = isr.index("ieee80211_tx_status_irqsafe(hw, skb);")
    wake = isr.index("ieee80211_wake_queue(hw, queue_mapping);")
    assert saved < status < wake


def test_guard_remains_be_only_and_target_gated() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "hgw500_tx_queue_guard && prio == BE_QUEUE" in text
    assert "hgw500_tx_queue_guard && hw_queue == BE_QUEUE" in text

