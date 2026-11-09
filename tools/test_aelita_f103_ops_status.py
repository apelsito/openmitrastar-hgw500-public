from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "aelita_f103_ops_status.ps1"


def test_f103_ops_status_is_read_only_for_uart_and_flash() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    forbidden = (
        "[IO.Ports.SerialPort]::new",
        "SerialPort",
        "mtd_debug",
        "flash_erase",
        "Start-Process",
        "ssh_openmitrastar_510.ps1",
        "reboot",
    )
    for needle in forbidden:
        assert needle not in text


def test_f103_ops_status_reports_operational_decision_surface() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    for needle in (
        "F103_ARMED_WAITING_UART_RX_ZERO_BYTES",
        "F103_BOOTBASE_CAPTURED_FLASH_ACTIVE",
        "F103_FLASH_READBACK_PASS",
        "expected_full_slot_crc32",
        "50cfcf29",
        "blind_space_count",
        "uart",
        "router",
        "aelita",
    ):
        assert needle in text
