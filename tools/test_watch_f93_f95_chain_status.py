#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tools/watch_f93_f95_chain_status.ps1"
ENSURE = ROOT / "tools/ensure_f93_f95_status_watch.ps1"


def test_watch_f93_f95_status_is_non_uart_status_only() -> None:
    text = WATCH.read_text(encoding="ascii")
    assert "status_f93_f95_chain.ps1" in text
    assert "latest.json" in text
    assert "history.jsonl" in text
    assert "Test-TcpPort" in text
    assert "router_tcp22" in text
    assert "uart_zero_bytes_stale" in text
    assert "OMF93F95_STATUS_WATCH" in text
    assert "SerialPort" not in text
    assert "COM3" not in text
    assert "spi_flash" not in text


def test_watch_f93_f95_status_has_terminal_chain_states() -> None:
    text = WATCH.read_text(encoding="ascii")
    assert '"pass"' in text
    assert '"f93_failed"' in text
    assert '"f95_failed_f93_fallback_armed"' in text
    assert '"timeout"' in text


def test_ensure_f93_f95_status_watch_is_idempotent() -> None:
    text = ENSURE.read_text(encoding="ascii")
    assert "watch_f93_f95_chain_status.ps1" in text
    assert "already_running" in text
    assert "started" in text
    assert "Get-OutputDirFromCommand" in text
    assert '"-File", $WatchScript' in text
    assert "-WindowStyle Hidden" in text
    assert "Get-CimInstance Win32_Process" in text
    assert "scriptblock|PARSE_OK" in text
    assert "ensure_f93_f95_status_watch" in text
