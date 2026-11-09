from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/rollback_f319_to_f314_mtd4.ps1"


def test_source_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OPENMITRASTAR_F319_ROLLBACK_TO_F314_A0C7350A" in source
    assert "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11" in source
    assert "22d3802a" in source
    assert "ad8bd328147e9fb03715b258bb99c69bbf0daa3b9c6a4dc993c0365ef7665601" in source
    assert 'target = "mtd4/linux_live"' in source
    assert 'mtd3/linux_safety' not in source
    assert "post_flash_f214_device_gate.py" in source
    assert 'Enter-F319HardwareGuard' in source
    assert 'Assert-F319UartBinding' in source
    assert 'ExpectedPnpDeviceId' in source
    assert source.index('Enter-F319HardwareGuard') < source.index('reboot_to_topaz_prompt_sysrq.ps1')
    assert source.index('Assert-F319UartBinding') < source.index('reboot_to_topaz_prompt_sysrq.ps1')


def test_dry_run() -> None:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    plan = json.loads(result.stdout)
    assert plan["mode"] == "dry-run"
    assert plan["target"] == "mtd4/linux_live"
    assert plan["local_preflight_pass"] is True
    assert plan["hardware_actions_performed"] is False
