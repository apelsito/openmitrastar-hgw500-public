#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f94_2g_mcs15_ht40sgi_descfix_after_f93.ps1"


def test_f94_flash_wrapper_points_at_f94_build_and_f93_current_crc() -> None:
    text = FLASH.read_text(encoding="ascii")
    assert "q3-persistent-composite-f94-2g-mcs15-ht40sgi-descfix-after-f93\\build" in text
    assert "OPENMITRASTAR_Q3_F94_2G_MCS15_HT40SGI_DESCFIX_AFTER_F93_MTD4_FLASH" in text
    assert '[string]$CurrentLiveCrc32 = "b68554e2"' in text
    assert "OMF94_FLASH_WRAPPER_DRY_RUN_PASS=1" in text
    assert "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py" in text
