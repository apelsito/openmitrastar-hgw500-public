#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = (
    ROOT
    / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
)


def test_mgmt_reply_rate_override_is_opt_in_and_target_gated() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")

    for needle in (
        "static unsigned int hgw500_mgmt_reply_rate;",
        "module_param_named(hgw500_mgmt_reply_rate,",
        "0=off, 1=1M, 2=2M, 6=6M, 11=11M",
        'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
        "rtl92ee_hgw500_mgmt_reply_desc_rate(",
        "ptcb_desc->packet_bw = HT_CHANNEL_WIDTH_20;",
        "ptcb_desc->use_shortgi = false;",
        "OMRTLMGMT stage=force-reply-rate",
    ):
        assert needle in text


def test_mgmt_reply_rate_override_scope_excludes_data_and_probe_response() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    helper = text[
        text.index("static bool rtl92ee_hgw500_mgmt_reply_desc_rate"):
        text.index("static bool rtl92ee_hgw500_trace_mgmt_frame")
    ]

    assert "ieee80211_is_auth(fc)" in helper
    assert "ieee80211_is_assoc_resp(fc)" in helper
    assert "ieee80211_is_reassoc_resp(fc)" in helper
    assert "ieee80211_is_probe_resp(fc)" not in helper
    assert "ieee80211_is_data" not in helper
