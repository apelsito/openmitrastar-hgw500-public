from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "arm_f122_5g_beacon_lifetime_flash.ps1"
FLASH_BACKEND = ROOT / "tools" / "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"


def test_f122_wrapper_is_pinned_to_exact_candidate_and_current_f121_slot() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "OPENMITRASTAR_Q3_F122_5G_BEACON_LIFETIME_FROM_F121_MTD4_FLASH_B760432B" in text
    assert "b760432b67b769701de0470d165132ba202074b82ba76b438e5ab85169742dab" in text
    assert '$ExpectedBytes = "4372386"' in text
    assert '$ExpectedCandidateCrc32 = "c68ac72a"' in text
    assert '$ExpectedFullSlotCrc32 = "fc3c3d99"' in text
    assert '[string]$CurrentLiveCrc32 = "a53e2c51"' in text


def test_f122_wrapper_uses_existing_bootbase_autobreak_backend() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1" in text
    assert "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py" in text
    assert "-AllowBlindAutobreak" in text
    assert "-AllowNoRxRebootAssist" in text
    assert "-SshRebootFirst" in text
    assert "-ConsoleRebootAssist" in text
    assert "-NoRxAbortSeconds" in text


def test_flash_backend_accepts_manifest_fixed_size_compensation_contract() -> None:
    text = FLASH_BACKEND.read_text(encoding="utf-8")

    assert 'fixed_size_compensation = manifest.get("patch", {}).get("fixed_size_compensation", {})' in text
    assert 'fixed_size_compensation.get("raw_bytes_preserved") is True' in text
    assert 'fixed_size_compensation.get("cpio_end_preserved") is True' in text
