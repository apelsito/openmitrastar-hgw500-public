#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX_C = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
TRX_H = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.h"


def helper_body(text: str, name: str) -> str:
    start = text.index(f"static inline void {name}")
    end = text.index("\n}", start) + 2
    return text[start:end]


def mcs15_block() -> str:
    text = TRX_C.read_text(encoding="utf-8", errors="replace")
    start = text.index("else if (hgw500_force_data_mcs15")
    end = text.index("if (info->flags & IEEE80211_TX_CTL_AMPDU)", start)
    return text[start:end]


def test_tx_rate_bw_and_shortgi_bits_do_not_overlap() -> None:
    text = TRX_H.read_text(encoding="utf-8", errors="replace")
    assert "u32 txbw:1;" in text
    assert "u32 txrate:6;" in text
    assert "u32 shortgi:1;" in text
    assert "GENMASK(5, 0)" in helper_body(text, "set_tx_desc_tx_rate")
    assert "GENMASK(6, 0)" not in helper_body(text, "set_tx_desc_tx_rate")
    assert "(__pdesc + 3)" in helper_body(text, "set_tx_desc_data_bw")
    assert "BIT(24)" in helper_body(text, "set_tx_desc_data_bw")
    assert "(__pdesc + 4)" in helper_body(text, "set_tx_desc_shortgi")
    assert "BIT(6)" in helper_body(text, "set_tx_desc_shortgi")


def test_force_mcs15_ht40sgi_is_opt_in_and_capability_gated() -> None:
    text = TRX_C.read_text(encoding="utf-8", errors="replace")
    block = mcs15_block()
    assert "static bool hgw500_force_data_ht40sgi;" in text
    assert "module_param_named(hgw500_force_data_ht40sgi" in text
    assert "hgw500_force_data_ht40sgi && bw_40" in block
    assert "ptcb_desc->packet_bw = HT_CHANNEL_WIDTH_20_40;" in block
    assert "sta->ht_cap.cap & IEEE80211_HT_CAP_SGI_40" in block
    assert "set_tx_desc_tx_rate(pdesc, DESC_RATEMCS15);" in block
    assert "ht40sgi=%u pkt_bw=%u shortgi=%u bw40=%u" in block


def test_shortgi_descriptor_is_written_after_bw_selection() -> None:
    text = TRX_C.read_text(encoding="utf-8", errors="replace")
    bw_pos = text.index("if (bw_40) {")
    sgi_pos = text.index("set_tx_desc_shortgi(pdesc, ptcb_desc->use_shortgi ? 1 : 0);")
    linip_pos = text.index("set_tx_desc_linip(pdesc, 0);")
    assert bw_pos < sgi_pos < linip_pos
