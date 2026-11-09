#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
OEM = ROOT / (
    "work/sources/rtl8198c-rtk-ref/rtk_openwrt_sdk/target/linux/realtek/"
    "files/drivers/net/wireless/rtl8192cd/WlanHAL/RTL88XX/Hal88XXTxDesc.c"
)


def test_split_is_opt_in_be_legacy64_and_target_only() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    assert "static bool hgw500_txbd_be_data_split;" in text
    assert "module_param_named(hgw500_txbd_be_data_split" in text
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "queue_index == BE_QUEUE" in text
    assert "buffer_desc_stride == 64" in text
    assert "append_early_mode_size == 0" in text
    assert "ieee80211_is_data(frame_control)" in text


def test_split_uses_header_llc_and_payload_segments() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    assert "split_header_len = ieee80211_hdrlen(frame_control);" in text
    assert "frame[split_header_len] == 0xaa" in text
    assert "split_header_len += 8;" in text
    assert "set_txbuffer_desc_len_with_offset(tx_bd_desc, 1," in text
    assert "set_txbuffer_desc_len_with_offset(tx_bd_desc, 2," in text
    assert "addr + split_header_len" in text
    assert "OMRTLTXBD stage=be-data-split" in text


def test_split_preserves_psb_own_doorbell_and_reclaim() -> None:
    text = TRX.read_text(encoding="utf-8", errors="replace")
    function = text[text.index("void rtl92ee_pre_fill_tx_bd_desc") : text.index("void rtl92ee_tx_fill_desc")]
    assert function.index("set_tx_buff_desc_psb(tx_bd_desc, psblen);") < function.index("if (split_be_data)")
    assert "set_tx_buff_desc_own(tx_bd_desc, 0);" in function
    assert "rtl_write_word" not in function
    assert "cur_tx_rp" not in function
    assert "cur_tx_wp =" not in function


def test_oem_reference_splits_header_and_payload() -> None:
    text = OEM.read_text(encoding="utf-8", errors="replace")
    assert "hdrLen      = pdesc_data->hdrLen + pdesc_data->llcLen" in text
    assert "cur_txbd->TXBD_ELE[1].Dword0" in text
    assert "cur_txbd->TXBD_ELE[2].Dword0" in text
    assert "pdesc_data->pHdr" in text
    assert "pdesc_data->pBuf" in text

