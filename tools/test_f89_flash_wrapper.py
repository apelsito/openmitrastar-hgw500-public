#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/flash_f89_2g_rate_trace_after_f88.ps1"


def test_f89_flash_wrapper_points_at_f89_build_and_f88_current_crc() -> None:
    text = FLASH.read_text(encoding="ascii")
    assert "q3-persistent-composite-f89-2g-rate-trace-after-f88\\build" in text
    assert "OPENMITRASTAR_Q3_F89_2G_RATE_TRACE_AFTER_F88_MTD4_FLASH_3F582995" in text
    assert '[string]$CurrentLiveCrc32 = "ee219d02"' in text
    assert "OMF89_FLASH_WRAPPER_DRY_RUN_PASS=1" in text
    assert "OMF89_FLASH_WRAPPER_EXCEPTION" in text
    assert "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py" in text
    assert "q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1" in text
