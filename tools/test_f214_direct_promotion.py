from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_f214_wrapper_is_exact_and_mtd4_only() -> None:
    text = (ROOT / "tools/promote_f214_mtd4_direct.ps1").read_text(encoding="utf-8")
    assert "14c7daa540e0d9cb4107b36d4e860212e044e392c17746f674369ae847c167b3" in text
    assert "$expectedBytes = 5201920" in text
    assert 'target = "mtd4/linux_live"' in text
    assert 'transport = "UART Bootbase + TFTP"' in text
    assert "SshRebootFirst" in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text
    assert "mtd3/linux_safety via UART" not in text


def test_f214_gate_checks_identity_storage_web_and_radios() -> None:
    text = (ROOT / "tools/post_flash_f214_device_gate.py").read_text(encoding="utf-8")
    for marker in (
        "lyoko-foundation-3.0-f214-device",
        "rootfs_live",
        "lyoko_store",
        "RADIO2_STATE=ENABLED",
        "RADIO5_STATE=ready",
        "SSH_IDENTITY=present",
        "WEB_CREDENTIAL=loaded",
        "PACKAGE_VERIFIER=present",
        "login_page",
        "api_protected",
    ):
        assert marker in text


def test_topaz_capture_can_pulse_reset_lines() -> None:
    text = (ROOT / "tools/reboot_to_topaz_prompt_sysrq.ps1").read_text(encoding="utf-8")
    assert "[switch]$PulseResetLinesFirst" in text
    assert "$serial.DtrEnable = $true" in text
    assert "$serial.RtsEnable = $true" in text
    assert "OMUART_RESET_LINES_PULSED=1" in text
