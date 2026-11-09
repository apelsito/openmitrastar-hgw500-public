from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f247_package_catalog_physical_gate.py"


def test_f247_package_gate_dry_run_is_non_mutating() -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--output-dir", directory],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["persistent_writes"] is False
    assert payload["network_fetch"] is False
    assert payload["maintainer_scripts"] is False


def test_f247_package_gate_keeps_storage_and_execution_boundaries() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in ("view=update", "view=search", "view=info", "view=depends", "view=plan", "OPENMITRASTAR_LYOKO_PKG_INSTALL_V1", "OPENMITRASTAR_LYOKO_PKG_REMOVE_V1"):
        assert marker in source
    for forbidden in ("mtd_debug", "flash_erase", "fw_setenv", "lyoko-pkg exec", "wget ", "curl "):
        assert forbidden not in source
