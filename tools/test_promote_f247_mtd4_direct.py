from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/promote_f247_mtd4_direct.ps1"


def test_f247_promoter_dry_run_is_pinned_and_non_mutating() -> None:
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
    assert payload["target"] == "mtd4/linux_live"
    assert payload["sha256"] == "8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12"
    assert payload["erase_bytes"] == "0x005e0000"
    assert payload["preserved_store_bytes"] == "0x001c0000"


def test_f247_promoter_enforces_transport_and_partition_boundaries() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in ("OPENMITRASTAR_F247_INTEGRATED_8BD78674", "mtd4/linux_live", "--transport tftp", "--transport uart-ymodem", "automatic fallback refused", "OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256"):
        assert marker in source
    for forbidden in ("mtd3", "mtd5 write", "fw_setenv", "--erase-bytes 0x7a0000"):
        assert forbidden not in source
