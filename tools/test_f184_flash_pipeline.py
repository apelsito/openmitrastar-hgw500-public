from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/build_flash_test_f184_integrated.ps1"
GATE = ROOT / "tools/post_flash_f184_integrated_gate.py"


def test_wrapper_is_guarded_and_targets_only_mtd4() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert 'target = "mtd4/linux_live"' in text
    assert "reboot_to_topaz_prompt_sysrq.ps1" in text
    assert "--transport uart-ymodem --uart-attach-topaz" in text
    assert "post_flash_f184_integrated_gate.py" in text
    for forbidden in ("mtd3", "mtd5", "fw_setenv", "flash_erase"):
        assert forbidden not in text


def test_gate_requires_capability_registry_and_integrated_gate() -> None:
    text = GATE.read_text(encoding="utf-8")
    assert "post_flash_f179_integrated_gate.py" in text
    assert "lyoko-foundation-1.4-f184" in text
    assert "lyoko.api.capabilities/v1" in text
    assert "len(items) == 16" in text
    assert "packages.volatile_install" in text
    assert "firmware.update" in text
