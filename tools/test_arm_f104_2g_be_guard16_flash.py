from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "arm_f104_2g_be_guard16_flash.ps1"


def test_f104_arm_script_is_pinned_to_f104_candidate() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "q3-persistent-composite-f104-2g-be-guard16-from-f103" in text
    assert "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH" in text
    assert "OPENMITRASTAR_Q3_F104_2G_BE_GUARD16_FROM_F103_MTD4_FLASH_E49BA57A" in text
    assert "e49ba57ac78c439da1d4da0a2e312f864286ecf3d01242d000f6af88fe56aea3" in text
    assert "$ExpectedBytes = \"5614538\"" in text
    assert "$ExpectedCandidateCrc32 = \"e3100009\"" in text
    assert "$ExpectedFullSlotCrc32 = \"722f542f\"" in text


def test_f104_arm_script_defaults_to_f103_live_crc_and_requires_execute_for_flash() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert '[string]$CurrentLiveCrc32 = "50cfcf29"' in text
    assert "OMF104_AUTO_ARM_DRY_RUN_PASS=1" in text
    assert "OMF104_AUTO_ARMED=1" in text
    assert "if (-not $Execute)" in text
    assert text.index("if (-not $Execute)") < text.index("$proc = Start-Process")


def test_f104_arm_script_uses_environment_overrides_and_no_direct_mtd_writes() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    for marker in (
        "OM_Q3_FLASH_ACK",
        "OM_Q3_FLASH_BUILD_DIR",
        "OM_Q3_FLASH_CANDIDATE",
        "OM_Q3_FLASH_EXPECTED_SHA256",
        "OM_Q3_FLASH_EXPECTED_BYTES",
        "OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32",
    ):
        assert marker in text
    for forbidden in ("mtd_debug", "flash_erase", "nandwrite", "dd if=", "dd of="):
        assert forbidden not in text

