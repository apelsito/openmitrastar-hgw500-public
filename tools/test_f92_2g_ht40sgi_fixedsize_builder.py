#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f92_2g_ht40sgi_fixedsize_from_f90.py"
WRAPPER = ROOT / "tools/flash_f92_2g_ht40sgi_fixedsize_after_f90.ps1"


def test_f92_builder_is_fixed_size_ht40sgi_from_f90() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f90-2g-mcs15-trace-after-f89" in text
    assert 'PATCH_ENTRY = "usr/sbin/om-radio-start"' in text
    assert "'secondary_channel=1'" in text
    assert "'ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40][DSSS_CCK-40]'" in text
    assert "F92 patch must preserve usr/sbin/om-radio-start size" in text
    assert "F92 patch changed decompressed payload size" in text
    assert "F92 patch changed CPIO placement" in text
    assert "unchanged from F90" in text


def test_f92_builder_keeps_flash_disabled_in_manifest() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert '"flash": False' in text
    assert '"touches_router": False' in text
    assert '"opens_uart": False' in text


def test_f92_flash_wrapper_targets_f91_current_live_slot() -> None:
    text = WRAPPER.read_text(encoding="ascii")
    assert 'q3-persistent-composite-f92-2g-ht40sgi-fixedsize-after-f90' in text
    assert 'OPENMITRASTAR_Q3_F92_2G_HT40SGI_FIXEDSIZE_AFTER_F90_MTD4_FLASH' in text
    assert '[string]$CurrentLiveCrc32 = "58a4df89"' in text
    assert "OM_Q3_FLASH_SSH_KEY" in text
