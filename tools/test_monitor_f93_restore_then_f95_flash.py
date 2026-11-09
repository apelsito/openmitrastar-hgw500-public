#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/monitor_f93_restore_then_f95_flash.ps1"


def test_chain_waits_for_f93_before_launching_f95() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "waiting for F93 restore watcher to pass" in text
    assert '$state -eq "pass"' in text
    assert "flash_f95_2g_mcs15_ht40sgi_descfix_fixedsize_after_f93.ps1" in text
    assert "OPENMITRASTAR_Q3_F95_2G_MCS15_HT40SGI_DESCFIX_FIXEDSIZE_AFTER_F93_MTD4_FLASH" in text
    assert '"b68554e2"' in text


def test_chain_arms_f93_fallback_after_f95_failure() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "Start-F93FallbackFromF95" in text
    assert "flash_f93_2g_ht40sgi_hostapd_compat_fixedsize_after_f92.ps1" in text
    assert '"418c9e28"' in text
    assert "f95_failed_f93_fallback_armed" in text


def test_chain_preserves_unattended_bootbase_capture_options() -> None:
    text = SCRIPT.read_text(encoding="ascii")
    assert "-AllowBlindAutobreak" in text
    assert "-AllowInfiniteNoRxWait" in text
    assert "-SshRebootFirst" in text
    assert "post_flash_f65_radio_gate.ps1" in text
    assert "-Run2gProbe" in text
