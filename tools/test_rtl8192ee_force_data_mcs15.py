#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"


def candidate_block() -> str:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    start = text.index("if (hgw500_force_data_mcs15")
    end = text.index("if (info->flags & IEEE80211_TX_CTL_AMPDU)", start)
    return text[start:end]


def test_force_mcs15_is_opt_in_and_target_gated() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    assert "static bool hgw500_force_data_mcs15;" in text
    assert "module_param_named(hgw500_force_data_mcs15" in text
    block = candidate_block()
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in block
    assert "sta && ieee80211_is_data(fc)" in block
    assert "!is_multicast_ether_addr" in block
    assert "!rtlpriv->ra.is_special_data" in block


def test_force_mcs15_bypasses_only_firmware_rate_selection() -> None:
    block = candidate_block()
    assert "ptcb_desc->use_driver_rate = true;" in block
    assert "ptcb_desc->disable_ratefallback = false;" in block
    assert "set_tx_desc_tx_rate(pdesc, DESC_RATEMCS15);" in block
    assert "set_tx_desc_agg_enable" not in block
    assert "set_tx_desc_max_agg_num" not in block
    assert "rtl_write" not in block


def test_candidate_has_unambiguous_runtime_marker() -> None:
    assert (
        'OMRTLRA stage=force-data-rate target=hgw500 rate=MCS15 fallback=1'
        in candidate_block()
    )
