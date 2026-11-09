#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "work/kernel-port/linux-5.10/rtl8192ee-mitrastar-tx26-pbp-width-override.patch"
APPLY = ROOT / "tools/apply_topaz_linux_510_overlay.sh"


def test_tx26_is_target_gated_and_parameterized() -> None:
    text = PATCH.read_text(encoding="utf-8")
    assert 'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' in text
    assert "hgw500_force_txbd64_width" in text
    assert "hgw500_tx_pbp_256" in text
    assert "REG_PBP, 0x21" in text
    assert "wordtmp |= BIT(15)" in text


def test_overlay_applies_tx26_once() -> None:
    text = APPLY.read_text(encoding="utf-8")
    assert "hgw500_tx_pbp_256" in text
    assert "rtl8192ee-mitrastar-tx26-pbp-width-override.patch" in text
