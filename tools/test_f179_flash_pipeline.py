from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/build_flash_test_f179_integrated.ps1"
GATE = ROOT / "tools/post_flash_f179_integrated_gate.py"


def test_wrapper_targets_only_mtd4_and_acquires_bootbase() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert 'target = "mtd4/linux_live"' in text
    assert "reboot_to_topaz_prompt_sysrq.ps1" in text
    assert "--transport uart-ymodem --uart-attach-topaz" in text
    assert "post_flash_f179_integrated_gate.py" in text
    for forbidden in ("mtd3", "mtd5", "fw_setenv", "spi_flash erase"):
        assert forbidden not in text


def test_gate_proves_integrated_runtime_without_persistence() -> None:
    text = GATE.read_text(encoding="utf-8")
    for marker in (
        "NAPI_WEIGHT=128",
        "lyoko-pkg verify lyoko-netdiag",
        "lyoko-pkg install lyoko-netdiag",
        "lyoko-pkg exec lyoko-netdiag lyoko-netdiag",
        "lyoko-pkg remove lyoko-netdiag",
        "DATA_HASH_BEFORE=",
        "DATA_HASH_AFTER=",
    ):
        assert marker in text
    assert "/run/lyoko-packages/f179-gate" in text
    assert "signature_verified" in text
