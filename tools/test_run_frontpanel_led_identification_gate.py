from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_frontpanel_led_identification_gate.ps1"


def test_led_gate_is_dry_run_by_default() -> None:
    result = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["restoration"] == "mandatory snapshot restore"
    assert payload["mtd_writes"] is False
    assert payload["radio_changes"] is False


def test_led_gate_requires_ack_and_has_no_flash_surface() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in ("OPENMITRASTAR_FRONTPANEL_LED_IDENTIFY", "--diagnostic identify", "restored_exactly", "OMLED_IDENTIFY_PASS restored=1"):
        assert marker in source
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "reboot", "hostapd", "iwpriv"):
        assert forbidden not in source
