"""Exercise production capture process lifecycle with synthetic children only."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@pytest.mark.parametrize("engine", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_production_lifecycle_preserves_real_exit_code(tmp_path, engine, exit_code):
    source = (ROOT / "tools/run_f319_spi_owner_probe.ps1").read_text(encoding="utf-8")
    start = source.index('    $uart = Start-Process -FilePath "powershell.exe"')
    stop = source.index('    [void](Wait-F319UartCaptureReady', start)
    startup = source[start:stop]
    assert '[void]$uart.Handle' in startup
    start = source.index('    if ($uart -and -not $uart.HasExited) { $uart.WaitForExit')
    stop = source.index('    [void](Assert-F319UartCaptureComplete', start)
    completion = source[start:stop]
    assert '$uart.Refresh()' in completion
    # These are the real lifecycle lines, not the hardware probe entrypoint.
    assert not any(word in startup + completion for word in ('COM3', 'insmod', 'ssh.exe', 'capture_topaz_uart_resilient'))
    child = '$ProgressPreference="SilentlyContinue"; [Console]::Out.WriteLine("F319_SYNTHETIC_CHILD"); Start-Sleep -Milliseconds 300; exit ' + str(exit_code)
    encoded_child = base64.b64encode(child.encode("utf-16le")).decode("ascii")
    command = (
        "$ErrorActionPreference='Stop'\nSet-StrictMode -Version Latest\n"
        f"$OutputDir={quote(tmp_path)}\n"
        f"$uartCommandLine='-NoProfile -NonInteractive -EncodedCommand {encoded_child}'\n"
        "$UartSeconds=1\n$uart=$null\ntry {\n" + startup + completion +
        "@{exit_code=$uart.ExitCode;is_int=($uart.ExitCode -is [int]);exited=$uart.HasExited} | ConvertTo-Json -Compress\n"
        "} finally { if($uart){if(-not $uart.HasExited){$uart.Kill();[void]$uart.WaitForExit(3000)};$uart.Dispose()} }\n"
    )
    executable = shutil.which(engine)
    assert executable, f"Required Windows engine missing: {engine}"
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand",
         base64.b64encode(command.encode("utf-16le")).decode("ascii")],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report == {"exit_code": exit_code, "is_int": True, "exited": True}
    assert (tmp_path / "uart.stdout.log").read_text().strip() == "F319_SYNTHETIC_CHILD"
    assert not (tmp_path / "uart.stderr.log").read_text().strip()
