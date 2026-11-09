from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "aelita_passive_recovery_watch.ps1"


def test_passive_recovery_watch_is_rx_only_supervisor() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "openmitrastar.passive-recovery-watch/v1" in text
    assert "capture_topaz_uart_resilient.ps1" in text
    assert "writes_uart = $false" in text
    assert "starts_blind_autobreak = $false" in text
    assert "direct_flash = $false" in text


def test_passive_recovery_watch_does_not_flash_or_autobreak() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    forbidden = (
        "[IO.Ports.SerialPort]::new",
        "SerialPort]::new",
        "q3_f45_radio5_powerselect",
        "watch_flash_f103",
        "mtd_debug",
        "flash_erase",
        "nandwrite",
        "dd if=",
        "dd of=",
        "ATGU",
        "AllowBlindAutobreak",
    )
    for needle in forbidden:
        assert needle not in text


def test_passive_recovery_watch_reports_recovery_states() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "router_ssh_ready" in text
    assert "router_ping_ready" in text
    assert "uart_rx_seen" in text
    assert "waiting for UART RX bytes or router network recovery" in text
