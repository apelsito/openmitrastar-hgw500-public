#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/watch_f92_recovery_then_2g_gate.ps1"


def test_f92_postflash_gate_uses_existing_watchdir_and_no_flash() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "f92-armed-recovery-" in text
    assert "status.state -eq \"pass\"" in text
    assert "run_aelita_2g_wpa2_speed_router_probe.py" in text
    assert "analyze_rtl8192ee_tx_rate_trace.py" in text
    assert "router-ssh-radio-status.txt" in text
    assert "flash_f92_2g_ht40sgi_fixedsize_after_f90.ps1" not in text
    assert "mtd4_bootbase_flash" not in text
