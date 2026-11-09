from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/build_flash_test_f182_spi_probe.ps1"


def test_f182_requires_staged_f179_and_refuses_existing_store() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert 'required_current_firmware = "F179"' in text
    assert 'lyoko-foundation-1\\.3-f179' in text
    assert '"lyoko_store"' in text
    assert "prefix-preserving flasher is required" in text


def test_f182_only_uses_guarded_mtd4_pipeline() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert 'target = "mtd4/linux_live"' in text
    assert "reboot_to_topaz_prompt_sysrq.ps1" in text
    assert "--transport uart-ymodem --uart-attach-topaz" in text
    assert "post_flash_f182_spi_probe_gate.py" in text
    for forbidden in ("fw_setenv", "mtd_debug", "flash_erase", "mount /dev/mtdblock4"):
        assert forbidden not in text
