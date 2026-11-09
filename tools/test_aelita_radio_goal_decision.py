from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "aelita_radio_goal_decision.ps1"


def test_radio_goal_decision_is_read_only() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    forbidden = (
        "[IO.Ports.SerialPort]::new",
        "SerialPort",
        "Start-Process",
        "ssh_openmitrastar_510.ps1",
        "mtd_debug",
        "flash_erase",
        "nandwrite",
        "dd if=",
        "dd of=",
        "reboot",
        "qtnboot",
    )
    for needle in forbidden:
        assert needle not in text


def test_radio_goal_decision_tracks_f103_and_f104_contracts() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    for needle in (
        "openmitrastar.radio-goal-decision/v1",
        "f103-emac-rxrestart-63pokes-from-f101",
        "f104-2g-be-guard16-from-f103",
        "arm_f104_2g_be_guard16_flash.ps1",
        "50cfcf29",
        "722f542f",
        "WAITING_FOR_UART_RX",
        "F103_WATCHER_STUCK_UART_RX_ZERO_REOPEN",
        "F103_WATCHER_EXPIRED_UART_RX_ZERO",
        "F103_FLASHED_VERIFY_2G",
        "PASSIVE_UART_CAPTURE_WAIT_POWER_CYCLE",
        "F104_READY_AFTER_F103",
        "mtd4/linux_live",
        "mtd6/rootfs_live-logical",
    ):
        assert needle in text


def test_radio_goal_decision_keeps_com3_exclusive_for_f103_when_waiting() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "com3_owner_should_remain_f103" in text
    assert "rearm_f103_allowed" in text
    assert "keep F103 watcher as sole COM3 owner" in text
    assert "do not open COM3" in text
    assert "rearm one short F103 no-RX probe" in text
    assert "physical power-cycle after wiring is correct" in text
    assert "stuckBlindSpaceThreshold = 600" in text


def test_radio_goal_decision_understands_passive_uart_capture() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "capture_topaz_uart_resilient\\.ps1" in text
    assert "passive-after-watchstop-*" in text
    assert "passive_capture" in text
    assert "rx_only" in text
    assert "do not rearm blind autobreak" in text
