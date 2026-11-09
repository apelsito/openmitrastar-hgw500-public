from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/promote_f237_mtd4_direct.ps1"


def test_f237_promoter_is_exact_and_dry_run_by_default() -> None:
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
    assert payload["bytes"] == 5218304
    assert payload["sha256"] == "46d7ab2fe356742854533834f69081b90701b95f1c163c86cb4afcbbb24607ed"
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OPENMITRASTAR_F237_HARDENED_CONTROL_46D7AB2F" in source
    assert "--erase-bytes 0x5e0000" in source
    for forbidden in ('target = "mtd3', 'target = "mtd5', "fw_setenv"):
        assert forbidden not in source
