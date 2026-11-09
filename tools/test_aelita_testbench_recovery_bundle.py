from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/aelita-testbench/lyoko-aelita-testbench-recovery-20260902"
SCRIPT = BUNDLE / "repair_aelita_testbench.ps1"


def test_aelita_repair_is_dry_run_by_default() -> None:
    result = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["router_changes"] is False
    assert payload["firmware_changes"] is False
    assert payload["wifi_profile_changes"] is False


def test_aelita_repair_is_key_only_and_controller_scoped() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "LYOKO_AELITA_TESTBENCH_REPAIR" in source
    assert "administrators_authorized_keys" in source
    assert "-RemoteAddress $ControllerIp" in source
    assert "Set-Service sshd -StartupType Automatic" in source
    for forbidden in ("password", "netsh wlan add profile", "Restart-Computer", "Stop-Computer", "mtd"):
        assert forbidden not in source
