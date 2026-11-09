#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f90_2g_mcs15_trace_from_f89.py"


def test_f90_builder_is_f89_mcs15_trace_only() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f89-2g-rate-trace-after-f88" in text
    assert 'PATCH_ENTRY = "usr/sbin/om-radio-modules"' in text
    assert "hgw500_force_data_mcs7=1 hgw500_force_data_mcs15=0" in text
    assert "hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=1" in text
    assert "hgw500_tx_rate_trace=1" in text
    assert "hgw500_force_data_mcs7=Y hgw500_force_data_mcs15=N" in text
    assert "hgw500_force_data_mcs7=N hgw500_force_data_mcs15=Y" in text
    assert "radio2g_dma_rings_queues_bridge" in text
    assert "unchanged from F89" in text
    assert "hgw500_be_tx_summary" not in text


def test_f90_builder_keeps_flash_disabled_in_manifest() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert '"flash": False' in text
    assert '"touches_router": False' in text
    assert '"opens_uart": False' in text
