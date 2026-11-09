from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f237_flash_test_cycle.ps1"


def test_f237_cycle_is_one_command_and_dry_run_by_default() -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
    result = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["target"] == "mtd4/linux_live"
    assert payload["candidate_sha256"] == "46d7ab2fe356742854533834f69081b90701b95f1c163c86cb4afcbbb24607ed"
    source = SCRIPT.read_text(encoding="utf-8")
    assert "promote_f237_mtd4_direct.ps1" in source
    assert "run_f237_dual_radio_control_postflash_gate.ps1" in source
    assert "OPENMITRASTAR_F237_FLASH_TEST_46D7AB2F" in source
    assert 'target = "mtd4/linux_live"' in source
