from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_uart_loader_is_ram_only_and_integrity_gated() -> None:
    text = (ROOT / "tools/uart_ymodem_load.py").read_text(encoding="utf-8")
    assert "loady" in text
    assert "printenv filesize" in text
    assert "Verifying Checksum ... OK" in text
    assert "expected-crc32" in text
    assert "spi_flash erase" not in text
    assert "spi_flash write" not in text


def test_bootbase_writer_supports_preloaded_uart_candidate() -> None:
    text = (
        ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1"
    ).read_text(encoding="utf-8")
    assert "[switch]$SkipNetworkTransfer" in text
    assert "OMLYOKO_UART_PRELOADED_CANDIDATE_PASS=1" in text
    assert "spi_flash erase 0x{0:x8} 0x{1:x8}" in text
    assert "$TargetOffset = 0x007e0000" in text
    assert "$TargetBytes = 0x007a0000" in text


def test_canonical_pipeline_defaults_to_uart_ymodem() -> None:
    text = (ROOT / "tools/build_flash_test_lyoko.ps1").read_text(encoding="utf-8")
    assert '[string]$Transport = "uart-ymodem"' in text
    assert "--transport $Transport" in text
    assert "--timeout 1800" in text


def test_runner_never_combines_attach_and_sysrq() -> None:
    text = (
        ROOT / "tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
    ).read_text(encoding="utf-8")
    loader_literal = text[text.index("loader_command = ["):text.index("]\n            if args.uart_attach_topaz", text.index("loader_command = ["))]
    assert '"--reboot-sysrq"' not in loader_literal
    assert 'loader_command.append("--reboot-sysrq")' in text
    assert 'loader_command.append("--receiver-ready" if args.uart_receiver_ready else "--attach-topaz")' in text


def test_postflash_gate_waits_for_both_radio_control_planes() -> None:
    text = (ROOT / "tools/post_flash_f164_squashfs_gate.py").read_text(encoding="utf-8")
    assert "hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 ping" in text
    assert '"radio2g": bool(re.search' in text
    assert "expected-rootfs-size" in text
