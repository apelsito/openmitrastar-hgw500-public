from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "arm_f97_emac_periodic_rxrestart_flash.ps1"
STATUS = ROOT / "tools" / "status_f97_flash_watch.ps1"
OPS_STATUS = ROOT / "tools" / "aelita_f97_ops_status.ps1"


def test_f97_wrapper_uses_console_reboot_assist_for_live_linux_uart() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "OPENMITRASTAR_Q3_F97_EMAC_PERIODIC_RXRESTART_FROM_F96_MTD4_FLASH_9A6BEDE8" in text
    assert "9a6bede8e209957990558060be9b67948b09480775e63a42e9b392ab3420022e" in text
    assert "-AllowBlindAutobreak" in text
    assert "-AllowNoRxRebootAssist" in text
    assert "-SysRqRebootFirst" in text
    assert "-SysRqRetrySeconds 5" in text
    assert "-ConsoleRebootAssist" in text
    assert "-ConsoleRebootRetrySeconds 5" in text


def test_f97_wrapper_keeps_default_no_rx_abort_disabled_for_connected_uart() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "-NoRxAbortSeconds 0" in text
    assert "F97 flash watcher armed; power-cycle target to flash" in text


def test_f97_wrapper_exposes_optional_uart_reset_line_pulse() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "[switch]$PulseResetLinesFirst" in text
    assert '$pulseResetArg = if ($PulseResetLinesFirst)' in text
    assert '-PulseResetLinesFirst" } else { "" }' in text
    assert "5$pulseResetArg" in text


def test_f97_status_finds_consoleassist_postflash_directory() -> None:
    text = STATUS.read_text(encoding="utf-8")

    assert 'f97-flash-then-2g-gate-*' in text
    assert 'f97-consoleassist-flash-then-2g-gate-*' in text
    assert 'f97-pulsereset-flash-then-2g-gate-*' in text


def test_f97_status_classifies_kernel_still_running_power_cycle_case() -> None:
    text = STATUS.read_text(encoding="utf-8")

    assert "WAITING_REAL_POWER_CYCLE_KERNEL_STILL_RUNNING" in text
    assert "BOOTBASE_CAPTURED_OR_FLASH_ACTIVE" in text
    assert "POSTFLASH_RESULT_EXISTS" in text
    assert "linux_console_seen" in text
    assert "sysrq_reboot_sent" in text
    assert "console_reboot_probe_sent" in text
    assert "blind_space_sent" in text
    assert "physical power-cycle HGW while keeping COM3 connected" in text


def test_f97_ops_status_surfaces_next_action_and_f98_readiness() -> None:
    text = OPS_STATUS.read_text(encoding="utf-8")

    assert "openmitrastar.aelita-f97-ops-status/v1" in text
    assert "F97_WAITING_REAL_POWER_CYCLE_KERNEL_STILL_RUNNING" in text
    assert "physical power-cycle HGW while keeping COM3 connected" in text
    assert "q3-persistent-composite-f98-2g-reclaim-poll-from-f97" in text
    assert "f98_ready_next" in text
    assert "status_f97_flash_watch.ps1" in text
