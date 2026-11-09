#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f90_2g_mcs15_trace_after_f89.ps1"


def test_f90_flash_wrapper_points_at_f90_build_and_f89_current_crc() -> None:
    text = FLASH.read_text(encoding="ascii")
    assert "q3-persistent-composite-f90-2g-mcs15-trace-after-f89\\build" in text
    assert "OPENMITRASTAR_Q3_F90_2G_MCS15_TRACE_AFTER_F89_MTD4_FLASH_65771911" in text
    assert '[string]$CurrentLiveCrc32 = "bfdd9c30"' in text
    assert "OMF90_FLASH_WRAPPER_DRY_RUN_PASS=1" in text
    assert "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py" in text
    assert "q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1" in text
