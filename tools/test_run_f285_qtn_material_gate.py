from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f285_qtn_material_gate.py"


def test_material_gate_dry_run_is_bounded() -> None:
    proc = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "openmitrastar.f285-qtn-material-gate-plan/v1"
    assert payload["change"] == {"ssid": True, "channel": False, "bandwidth": False, "psk": False}
    assert payload["flash"] is False
    assert payload["mtd_writes"] is False


def test_material_gate_has_no_automatic_retry_or_flash_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"automatic_retry": False' in source
    assert '"watchdog_present": True' in source
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source
