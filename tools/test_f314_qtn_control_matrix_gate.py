from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tools/run_f313_qtn_control_matrix_gate.py"
F314 = ROOT / "tools/run_f314_qtn_control_matrix_gate.py"


def test_f314_wrapper_pins_release_identity() -> None:
    text = F314.read_text(encoding="utf-8")
    assert "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device" in text
    assert 'gate.RELEASE = "f314"' in text
    assert "known_hosts.f314" in text
    assert "f314-qtn-control-matrix" in text


def test_gate_has_timeout_safe_rollback_and_resume() -> None:
    text = BASE.read_text(encoding="utf-8")
    assert 'parser.add_argument("--resume", action="store_true")' in text
    assert "if not rolled_back:" in text
    assert "emergency rollback failed" in text
    assert 'ssh(args.host, args.known_hosts, "true")' in text
    assert 'not health["radio2_ready"]' in text
    assert 'not health["radio5_ready"]' in text
    assert "applied_health = runtime_health(api)" in text
    assert "require_snapshot(applied_snapshot, expected_applied" in text
    assert "require_snapshot(restored_snapshot, baseline" in text
    assert 'ssh_state != "verified"' in text
    assert "ACTION_TIMEOUT = 360" in text


def test_f314_dry_run_contract() -> None:
    proc = subprocess.run(
        [sys.executable, str(F314)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert '"schema": "openmitrastar.f314-qtn-control-matrix-plan/v1"' in proc.stdout
    assert '"firmware": "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"' in proc.stdout
    assert '"flash": false' in proc.stdout
