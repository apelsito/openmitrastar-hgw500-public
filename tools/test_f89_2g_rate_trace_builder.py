#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f89_2g_rate_trace_from_f88.py"


def test_f89_builder_is_f88_fixed_offset_rate_trace_only() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f88-5g-bounded-marker-fix-after-f87" in text
    assert 'PATCH_ENTRY = "usr/sbin/om-radio-modules"' in text
    assert "hgw500_tx_rate_trace=0'" in text
    assert "hgw500_tx_rate_trace=1'" in text
    assert "hgw500_tx_rate_trace=N; do" in text
    assert "hgw500_tx_rate_trace=Y; do" in text
    assert "radio2g_rates_dma_rings_queues" in text
    assert "unchanged from F88" in text
    assert "OMRTLBE" not in text
    assert "hgw500_be_tx_summary" not in text


def test_f89_builder_keeps_flash_disabled_in_manifest() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert '"flash": False' in text
    assert '"touches_router": False' in text
    assert '"opens_uart": False' in text
