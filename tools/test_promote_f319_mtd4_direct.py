from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/promote_f319_mtd4_direct.ps1"


def test_source_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'OPENMITRASTAR_F319_MTD4_E33D8511' in source
    assert 'e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9' in source
    assert 'd6b13baa' in source
    assert 'bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989' in source
    assert 'write_target = "mtd4/linux_live"' in source
    assert 'OM_Q3_FLASH_ROOTFS_OFFSET = "0x180000"' in source
    assert 'run_f319_spi_owner_probe.ps1' in source
    assert 'reboot_to_topaz_prompt_sysrq.ps1' in source
    assert 'mtd0/mtd1/mtd2/mtd3/mtd5 unchanged' in source
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
    assert plan["write_target"] == "mtd4/linux_live"
    assert plan["local_preflight_pass"] is True
    assert plan["hardware_actions_performed"] is False
