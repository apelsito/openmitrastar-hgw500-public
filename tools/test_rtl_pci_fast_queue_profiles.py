#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"


def test_fast_profile_switches_are_target_gated() -> None:
    text = PCI.read_text(encoding="utf-8", errors="replace")
    assert "hgw500_txbd_tx5_layout" in text
    assert "hgw500_txbd_be_legacy64" in text
    assert "hgw500_tx_queue_guard" in text
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "prio == BE_QUEUE && hgw500_txbd_be_legacy64" in text
    assert "static unsigned int hgw500_tx_queue_guard_high = 64;" in text
    assert "static unsigned int hgw500_tx_queue_guard_low = 32;" in text
    assert "rtl_pci_hgw500_guard_high(ring)" in text
    assert "rtl_pci_hgw500_guard_low(ring)" in text
