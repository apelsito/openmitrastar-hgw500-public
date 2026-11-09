#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"


def test_mcs7_force_is_opt_in_target_gated_and_unicast_only() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    assert "static bool hgw500_force_data_mcs7;" in text
    assert "module_param_named(hgw500_force_data_mcs7" in text
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "sta && ieee80211_is_data(fc)" in text
    assert "!rtlpriv->ra.is_special_data" in text
    assert "!is_multicast_ether_addr(ieee80211_get_DA(hdr))" in text


def test_mcs7_force_bypasses_opaque_firmware_ra_but_keeps_fallback() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    start = text.index("if (hgw500_force_data_mcs7")
    end = text.index("if (info->flags & IEEE80211_TX_CTL_AMPDU)", start)
    block = text[start:end]
    assert "ptcb_desc->hw_rate = DESC_RATEMCS7;" in block
    assert "ptcb_desc->packet_bw = HT_CHANNEL_WIDTH_20;" in block
    assert "ptcb_desc->use_shortgi = false;" in block
    assert "ptcb_desc->use_driver_rate = true;" in block
    assert "ptcb_desc->disable_ratefallback = true;" in block
    assert "set_tx_desc_tx_rate(pdesc, ptcb_desc->hw_rate);" in block
    assert "rate=MCS7 nss=1 fallback=0 dis_fb=1 pkt_bw=20 shortgi=0" in block
    assert "else if (hgw500_force_data_11m" in block


def test_mcs7_force_preserves_ampdu_and_descriptor_geometry() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    start = text.index("if (hgw500_force_data_mcs7")
    end = text.index("if (info->flags & IEEE80211_TX_CTL_AMPDU)", start)
    block = text[start:end]
    for forbidden in (
        "set_tx_desc_agg_enable",
        "set_tx_desc_max_agg_num",
        "set_tx_buff_desc",
        "cur_tx_wp",
        "cur_tx_rp",
        "rtl_write",
    ):
        assert forbidden not in block
