#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_5g_assoc_only_oracle.ps1"
TASK = ROOT / "tools/start_qtn_5g_assoc_only_oracle_task.ps1"


def _parse_powershell(path: Path) -> None:
    escaped = str(path).replace("'", "''")
    command = (
        "$e=$null;$t=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count){$e|ForEach-Object{$_.ToString()};exit 1}"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_assoc_only_oracle_parses() -> None:
    _parse_powershell(SCRIPT)
    _parse_powershell(TASK)


def test_assoc_only_oracle_dry_run_is_network_free() -> None:
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OMQTN5G_ASSOC_ONLY_ORACLE_DRY_RUN_PASS=1" in proc.stdout
    assert '"association_only":  true' in proc.stdout
    assert '"static_ip_allowed":  false' in proc.stdout
    assert '"ping_allowed":  false' in proc.stdout
    assert '"traffic_allowed":  false' in proc.stdout


def test_assoc_only_oracle_contract_is_scan_connect_restore_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "OPENMITRASTAR_QTN_5G_ASSOC_ONLY_ORACLE",
        "'wlan', 'show', 'networks', 'mode=bssid'",
        "'wlan', 'add', 'profile'",
        "'wlan', 'connect'",
        "Wait-CurrentSsid",
        "PASS_ASSOC_ONLY",
        "FAIL_NOT_VISIBLE",
        "FAIL_CONNECT",
        "FAIL_RESTORE",
        "scan_and_association_only_no_l3_no_traffic",
        "Save-OracleResult -Data $result",
    ):
        assert marker in text

    forbidden = (
        "ssh",
        "ramssh",
        "COM3",
        "Set-NetIPInterface",
        "New-NetIPAddress",
        "Get-NetIPAddress",
        "ping.exe",
        "curl.exe",
        "Start-ScheduledTask",
        "flash_erase",
        "mtd_debug",
        "fw_setenv",
    )
    lowered = text.lower()
    for needle in forbidden:
        assert needle.lower() not in lowered


def test_restore_happens_before_final_result_write() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    finally_at = text.index("} finally {")
    restore_at = text.index("$restore = Invoke-Netsh", finally_at)
    write_at = text.index("Save-OracleResult -Data $result", restore_at)
    assert restore_at < write_at


def test_assoc_only_task_dry_run_and_watchdog_contract() -> None:
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TASK)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OMQTN5G_ASSOC_ONLY_TASK_DRY_RUN_PASS=1" in proc.stdout
    text = TASK.read_text(encoding="utf-8")
    for marker in (
        "OPENMITRASTAR_QTN_5G_ASSOC_ONLY_TASK",
        "New-ScheduledTaskPrincipal -UserId 'SYSTEM'",
        "restore_wifi_oracle_watchdog.ps1",
        "SYSTEM restore-watchdog preflight produced no status file",
        "watchdog_preflight = 'passed-as-SYSTEM'",
        "run_qtn_5g_assoc_only_oracle.ps1",
        "OPENMITRASTAR_QTN_5G_ASSOC_ONLY_ORACLE",
        "router_mutations = $false",
        "serial_uart = $false",
        "flash = $false",
    ):
        assert marker in text
    assert text.index("Register-ScheduledTask -TaskName $watchdogTaskName") < text.index(
        "Register-ScheduledTask -TaskName $taskName"
    )


def test_assoc_only_task_does_not_reference_router_or_flash_tools() -> None:
    text = TASK.read_text(encoding="utf-8").lower()
    forbidden = (
        "192.168.1.90",
        "com3",
        "flash_erase",
        "mtd_debug",
        "fw_setenv",
        "set-netipinterface",
        "new-netipaddress",
        "ping.exe",
        "curl.exe",
    )
    for needle in forbidden:
        assert needle not in text
