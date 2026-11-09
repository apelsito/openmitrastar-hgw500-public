from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/find_aelita_testbench.ps1"


def test_discovery_is_read_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in ("Get-NetNeighbor", "SendPingAsync", "CC-6B-1E-77-2D-5B", "48-9E-BD-4D-3B-C4", "FOUND_SSH", "FOUND_NO_SSH", "NOT_FOUND"):
        assert marker in source
    for forbidden in ("Set-NetIP", "New-NetIPAddress", "Remove-Net", "Restart-Computer", "Stop-Computer", "ssh.exe", "mtd"):
        assert forbidden not in source


def test_discovery_parses_and_runs_without_active_probe() -> None:
    result = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 20, 21}, result.stdout + result.stderr
    assert '"schema": "openmitrastar.aelita-discovery/v1"' in result.stdout
