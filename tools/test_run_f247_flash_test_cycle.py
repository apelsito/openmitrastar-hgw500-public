from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT / "tools/run_f247_flash_test_cycle.ps1"
CONTROL = ROOT / "tools/run_f247_dual_radio_control_postflash_gate.ps1"
RADIO2 = ROOT / "tools/run_f247_physical_campaign.ps1"


def run_dry(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args], cwd=ROOT, text=True, capture_output=True, check=False)


def test_f247_full_cycle_dry_run_reports_current_preflight_without_flash() -> None:
    result = run_dry(CYCLE)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["target"] == "mtd4/linux_live"
    assert payload["candidate_contract"] is True
    assert payload["rollback_artifact"] is True
    assert payload["stop_on_first_failure"] is True
    assert payload["automatic_reflash"] is False


def test_f247_component_gates_are_dry_run_safe() -> None:
    control = run_dry(CONTROL)
    radio2 = run_dry(RADIO2)
    assert control.returncode == 0, control.stdout + control.stderr
    assert radio2.returncode == 0, radio2.stdout + radio2.stderr
    assert json.loads(control.stdout)["flash"] is False
    assert json.loads(radio2.stdout)["flash"] is False


def test_f247_cycle_requires_preflight_before_flash_and_exact_ack() -> None:
    source = CYCLE.read_text(encoding="utf-8")
    preflight_index = source.index('foreach ($required in')
    flash_index = source.index('promote_f247_mtd4_direct.ps1')
    assert preflight_index < flash_index
    for marker in ("OPENMITRASTAR_F247_FULL_CYCLE_8BD78674", "oracle_ssh", "controller_tcp", "uart_present", "restore_f222_mtd4_from_f247.ps1", "stop_on_first_failure"):
        assert marker in source
    assert "automatic_reflash=$false" in source
