import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "restore_wifi_oracle_watchdog.ps1"


def test_watchdog_parses_without_execution():
    escaped = str(SCRIPT).replace("'", "''")
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


def test_watchdog_is_local_idempotent_and_verified():
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "Test-Restored",
        "already_restored",
        "profile_available",
        "Get-NetConnectionProfile -InterfaceAlias $WifiInterface",
        "wlan connect",
        "Restore profile unavailable to SYSTEM",
        "Save-WatchdogStatus",
        "exit 20",
    ):
        assert marker in text
    for forbidden in ("Invoke-WebRequest", "Invoke-RestMethod", "ssh.exe", "WinRM"):
        assert forbidden not in text
