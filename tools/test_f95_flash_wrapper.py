#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f95_2g_mcs15_ht40sgi_descfix_fixedsize_after_f93.ps1"


def test_f95_flash_wrapper_points_at_fixedsize_build_and_f93_current_crc() -> None:
    text = FLASH.read_text(encoding="ascii")
    assert "q3-persistent-composite-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93\\build" in text
    assert "OPENMITRASTAR_Q3_F95_2G_MCS15_HT40SGI_DESCFIX_FIXEDSIZE_AFTER_F93_MTD4_FLASH" in text
    assert '[string]$CurrentLiveCrc32 = "b68554e2"' in text
    assert "OMF95_FLASH_WRAPPER_DRY_RUN_PASS=1" in text
    assert "[switch]$AllowBlindAutobreak" in text
    assert "$q3Params.AllowBlindAutobreak = $true" in text
    assert "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py" in text
