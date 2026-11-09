#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/status_f93_f95_chain.ps1"


def test_status_reports_uart_age_blind_count_and_recommendation() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "age_seconds" in text
    assert "uart_zero_bytes_stale" in text
    assert "OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT" in text
    assert "blind_space_count" in text
    assert "WAITING_FOR_PHYSICAL_POWER_CYCLE_OR_ROUTER_TX_TO_FTDI_RX" in text
    assert "recommendation" in text
    assert "next_action" in text
    assert "Do not start a second COM3 owner." in text


def test_status_uses_latest_chain_and_f93_directories() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "[string]$ChainOutputDir" in text
    assert "$ChainDir = $ChainOutputDir" in text
    assert 'Get-LatestDir "f93-restore-then-f95-*"' in text
    assert 'Get-LatestDir "f93-restore-*"' in text
    assert "chain-status.json" in text
    assert "status.json" in text
