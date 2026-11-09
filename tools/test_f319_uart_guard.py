from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools/f319_uart_guard.ps1"
CAPTURE = ROOT / "tools/capture_topaz_uart_resilient.ps1"
REBOOT = ROOT / "tools/reboot_to_topaz_prompt_sysrq.ps1"


def test_guard_contract() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "Local\\OpenMitraStar-UART-" in source
    assert "Local\\OpenRouterLab-UART-" in source
    assert "Physical hardware lock is already held" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "OPENMITRASTAR_PRODUCT_VERSION=" in source
    assert "OMF319_UART_BIND_" in source
    assert ">/dev/console" in source
    assert "$serial.Write(" not in source


def test_capture_can_run_under_parent_ownership() -> None:
    source = CAPTURE.read_text(encoding="utf-8")
    assert "ExternalOwnershipHeld" in source
    assert "Local\\OpenMitraStar-UART-" in source
    assert "Local\\OpenRouterLab-UART-" in source
    assert "ExpectedPnpDeviceId" in source


def test_reboot_rechecks_pnp_before_opening_serial() -> None:
    source = REBOOT.read_text(encoding="utf-8")
    assert "ExpectedPnpDeviceId" in source
    assert source.index("PNPDeviceID -ine $ExpectedPnpDeviceId") < source.index("$serial.Open()")


def test_powershell_sources_parse() -> None:
    files = [GUARD, CAPTURE, REBOOT]
    quoted = ",".join("'" + str(path).replace("'", "''") + "'" for path in files)
    command = (
        "$failed=$false; foreach($path in @(" + quoted + ")) { "
        "$tokens=$null; $errors=$null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors); "
        "if($errors.Count -gt 0){$failed=$true; $errors | ForEach-Object { Write-Error $_.Message }} }; "
        "if($failed){exit 1}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
