from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "aelita_radio_goal_watchdog.ps1"


def test_watchdog_is_supervisor_not_flash_backend() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "openmitrastar.radio-goal-watchdog/v1" in text
    assert "touches_com3_directly = $false" in text
    assert "direct_flash = $false" in text
    assert "aelita_radio_goal_decision.ps1" in text
    assert "watch_post_f103_2g_gate.ps1" in text
    assert "watch_flash_f103_emac_rxrestart_until_bootbase.ps1" in text


def test_watchdog_only_rearms_f103_when_decision_allows() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert 'decisionName -eq "F103_WATCHER_EXPIRED_UART_RX_ZERO"' in text
    assert 'decisionName -eq "F103_WATCHER_STUCK_UART_RX_ZERO_REOPEN"' in text
    assert "Start-F103Watcher" in text
    assert "Restart-StuckF103Watcher" in text
    assert "already-running" in text
    assert "watch_flash_f103|q3_f45_radio5_powerselect" in text
    assert "watch_post_f103_2g_gate" in text
    assert '$F103NoRxAbortSeconds = 45' in text


def test_watchdog_avoids_direct_uart_and_mtd_writes() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    forbidden = (
        "[IO.Ports.SerialPort]::new",
        "SerialPort",
        "mtd_debug",
        "flash_erase",
        "nandwrite",
        "dd if=",
        "dd of=",
        "qtnboot",
    )
    for needle in forbidden:
        assert needle not in text
