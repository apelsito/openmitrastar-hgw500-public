import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUNDTRIP = ROOT / "tools" / "run_wifi_oracle_roundtrip.ps1"
STARTER = ROOT / "tools" / "start_wifi_oracle_roundtrip_task.ps1"


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
    )


def test_scripts_parse_without_execution():
    _parse_powershell(ROUNDTRIP)
    _parse_powershell(STARTER)


def test_roundtrip_restores_before_final_result_write():
    text = ROUNDTRIP.read_text(encoding="utf-8")
    finally_at = text.index("} finally {")
    restore_at = text.index("$restore = Invoke-Netsh", finally_at)
    write_at = text.index("Save-OracleResult -Data $result", restore_at)
    assert restore_at < write_at
    for marker in (
        "Wait-ExactWifiConnection",
        "Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias",
        "restore_command_exit_code",
        "restore_error",
        "exit $scriptExitCode",
        "'wlan', 'delete', 'profile'",
        "curl_exit_code",
        "ping_exit_code",
    ):
        assert marker in text
    # Windows curl rejected binding to the DHCP IPv4 literal with exit 45
    # during the first hardware roundtrip. Normal route selection is required.
    assert "--interface $ip" not in text


def test_starter_is_system_only_quoted_and_has_watchdog():
    text = STARTER.read_text(encoding="utf-8")
    for marker in (
        "Assert-ElevatedAdministrator",
        "Protect-SystemOnlyPath",
        "*S-1-5-18:F",
        "*S-1-5-32-544:F",
        "Get-FileHash -LiteralPath $script",
        "ConvertTo-EncodedPowerShell",
        "-EncodedCommand $oracleEncoded",
        "-EncodedCommand $restoreEncoded",
        "New-ScheduledTaskPrincipal -UserId 'SYSTEM'",
        "OpenMitraStar-WiFiOracle-Restore",
        "restore_wifi_oracle_watchdog.ps1",
        "-RepetitionInterval (New-TimeSpan -Minutes 2)",
        "-RepetitionDuration (New-TimeSpan -Minutes 20)",
        "-WakeToRun",
        "SYSTEM restore-watchdog preflight produced no status file",
        "watchdog_preflight = 'passed-as-SYSTEM'",
        "-StartWhenAvailable",
        "Start-ScheduledTask -TaskName $taskName",
        "AddMinutes(-5)",
        "must not be a reparse point",
        "contain no control characters",
    ):
        assert marker in text
    assert text.index("Register-ScheduledTask -TaskName $watchdogTaskName") < text.index(
        "Register-ScheduledTask -TaskName $taskName"
    )
    assert "-File " not in text
