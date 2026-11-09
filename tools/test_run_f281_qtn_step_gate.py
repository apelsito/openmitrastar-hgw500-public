from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f281_qtn_step_gate.py"


def dry_run(step: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--step", step],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_low_risk_preview_is_read_only() -> None:
    payload = dry_run("rf-write-same")
    assert payload["schema"] == "openmitrastar.f281-qtn-step-gate-plan/v1"
    assert payload["expected_version"] == "lyoko-foundation-6.3.5-f281-qtn-apply-fix-device"
    assert payload["risk"] == "low"
    assert payload["flash"] is False
    assert payload["writes_mtd"] is False
    assert payload["requires_physical_recovery"] is False


def test_mode_probe_requires_physical_recovery() -> None:
    payload = dry_run("mode-write-same")
    assert payload["risk"] == "management-loss-possible"
    assert payload["requires_physical_recovery"] is True


def test_gate_contains_no_flash_primitive() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv"):
        assert forbidden not in source
    assert "automatic_retry" in source
    assert '"automatic_recovery": False' in source
    assert "stable_radio_view" in source
    assert "state_preserved" in source
    assert "after-samples.json" in source
    assert "transient_state_observed" in source
    assert "FATAL_COUNT" in source
