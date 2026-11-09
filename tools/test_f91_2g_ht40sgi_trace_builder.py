#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f91_2g_ht40sgi_trace_from_f90.py"
WRAPPER = ROOT / "tools/flash_f91_2g_ht40sgi_trace_after_f90.ps1"


def test_f91_builder_is_f90_hostapd_ht40sgi_only() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f90-2g-mcs15-trace-after-f89" in text
    assert 'PATCH_ENTRY = "usr/sbin/om-radio-start"' in text
    assert "'ieee80211n=1'" in text
    assert "'secondary_channel=1'" in text
    assert "'ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40][DSSS_CCK-40]'" in text
    assert "radio2g_modules" in text
    assert "unchanged binaries from F90" in text
    assert "radio2g_rates" in text
    assert "forced MCS15" in text
    assert "qdrv" in text
    assert "unchanged from F90" in text


def test_f91_builder_keeps_flash_disabled_in_manifest() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert '"flash": False' in text
    assert '"touches_router": False' in text
    assert '"opens_uart": False' in text


def test_f91_flash_wrapper_targets_f90_current_live_slot() -> None:
    text = WRAPPER.read_text(encoding="ascii")
    assert 'q3-persistent-composite-f91-2g-ht40sgi-trace-after-f90' in text
    assert 'OPENMITRASTAR_Q3_F91_2G_HT40SGI_TRACE_AFTER_F90_MTD4_FLASH' in text
    assert '[string]$CurrentLiveCrc32 = "a0278d3f"' in text
    assert "OM_Q3_FLASH_SSH_KEY" in text
