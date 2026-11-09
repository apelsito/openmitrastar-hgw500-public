from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "arm_f105_2g_be_reclaim_kick_flash.ps1"


def test_f105_arm_script_is_pinned_to_f105_candidate() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "q3-persistent-composite-f105-2g-be-reclaim-kick-from-f104" in text
    assert "openmitrastar-linux510-q3-persistent-f105-2g-be-reclaim-kick-from-f104-LZMA-OFFLINE-NO-FLASH" in text
    assert "OPENMITRASTAR_Q3_F105_2G_BE_RECLAIM_KICK_FROM_F104_MTD4_FLASH_C464A54A" in text
    assert "c464a54a3c7687021d81f7af8ba58b73c72cf002a73383f2e1553db4980b4c93" in text
    assert "$ExpectedBytes = \"5612728\"" in text
    assert "$ExpectedCandidateCrc32 = \"e4518060\"" in text
    assert "$ExpectedFullSlotCrc32 = \"c85b668a\"" in text


def test_f105_arm_script_defaults_to_f104_live_crc_and_requires_execute() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert '[string]$CurrentLiveCrc32 = "722f542f"' in text
    assert "OMF105_AUTO_ARM_DRY_RUN_PASS=1" in text
    assert "OMF105_AUTO_ARMED=1" in text
    assert "if (-not $Execute)" in text
    assert text.index("if (-not $Execute)") < text.index("$proc = Start-Process")


def test_f105_arm_script_uses_flash_env_and_no_direct_mtd_writes() -> None:
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
