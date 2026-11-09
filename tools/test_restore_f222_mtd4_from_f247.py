from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/restore_f222_mtd4_from_f247.ps1"


def test_rollback_dry_run_targets_only_mtd4() -> None:
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
    assert payload["candidate_sha256"] == "ab8f8727f3b1c29a312eddb21f1aa5bc9f474d7be91569f57c9230aaf1fc1c21"
    assert payload["transport"] == "UART/YMODEM"
    assert "mtd3/linux_safety" in payload["protected"]


def test_rollback_requires_exact_ack_and_preserves_store_tail() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OPENMITRASTAR_RESTORE_F222_FROM_F247_AB8F8727" in source
    assert "OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256" in source
    assert "--erase-bytes 0x5e0000" in source
    for forbidden in ("fw_setenv", "--erase-bytes 0x7a0000", "mtd3 write", "mtd5 write"):
        assert forbidden not in source
