#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
FW = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/fw.c"


def test_rate_trace_is_opt_in_and_target_gated() -> None:
    trx = TRX.read_text(encoding="utf-8", errors="replace")
    fw = FW.read_text(encoding="utf-8", errors="replace")
    assert "bool rtl92ee_hgw500_tx_rate_trace;" in trx
    assert "module_param_named(hgw500_tx_rate_trace" in trx
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in trx
    assert "extern bool rtl92ee_hgw500_tx_rate_trace;" in fw
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in fw


def test_descriptor_trace_is_be_unicast_data_only_and_bounded() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    block = text[text.index("if (rtl92ee_hgw500_tx_rate_trace") : text.index("if (skb->len >= 24")]
    assert "hw_queue == BE_QUEUE" in block
    assert "sta && ieee80211_is_data(fc)" in block
    assert "!is_multicast_ether_addr" in block
    assert "event <= 32 || is_power_of_2(event)" in block
    assert "OMRTLRA stage=tx-desc" in block
    for field in ("hw_rate", "use_rate", "dis_fb", "ampdu", "shortgi", "pkt_bw", "d0=%08x", "d5=%08x"):
        assert field in block


def test_firmware_ra_trace_records_actual_rate_and_collision() -> None:
    text = FW.read_text(encoding="utf-8", errors="replace")
    block = text[text.index("void rtl92ee_c2h_ra_report_handler") :]
    assert "rate = cmd_buf[0] & 0x3F" in block
    assert "cmd_len >= 4" in block
    assert "cmd_buf[3] & BIT(0)" in block
    assert "OMRTLRA stage=fw-report" in block
    assert "rate=%u" in block
    assert "sgi=%u" in block
    assert "macid=%u" in block
    assert "collision=%u" in block
    assert "raw=%02x:%02x:%02x:%02x" in block


def test_trace_does_not_force_rate_or_change_aggregation() -> None:
    trx = TRX.read_text(encoding="utf-8", errors="replace")
    block = trx[trx.index("if (rtl92ee_hgw500_tx_rate_trace") : trx.index("if (skb->len >= 24")]
    forbidden = (
        "set_tx_desc_tx_rate",
        "set_tx_desc_use_rate",
        "set_tx_desc_agg_enable",
        "set_tx_desc_disable_fb",
        "rtl_write",
    )
    for needle in forbidden:
        assert needle not in block

