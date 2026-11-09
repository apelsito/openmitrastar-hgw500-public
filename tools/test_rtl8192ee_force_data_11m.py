#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"


def test_force_data_11m_is_target_gated_and_unicast_only() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    assert "hgw500_force_data_11m" in text
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "sta && ieee80211_is_data(fc)" in text
    assert "!rtlpriv->ra.is_special_data" in text
    assert "!is_multicast_ether_addr(ieee80211_get_DA(hdr))" in text
    assert "set_tx_desc_tx_rate(pdesc, DESC_RATE11M)" in text
    assert "ptcb_desc->use_driver_rate = true" in text
    assert "ptcb_desc->disable_ratefallback = false" in text
