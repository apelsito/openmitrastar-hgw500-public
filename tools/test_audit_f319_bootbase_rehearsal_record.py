"""Offline audit orchestration only; production proof semantics have their own tests."""
import base64
import json
from types import SimpleNamespace

import pytest

import audit_lyoko_full_liberation as audit


def test_missing_rehearsal_never_starts_reader(monkeypatch):
    monkeypatch.setattr(audit.subprocess, "run", lambda *a, **k: pytest.fail("unexpected process"))
    assert audit.verify_recorded_bootbase_rehearsal(None)["verified"] is False


def test_uses_only_production_file_reader(monkeypatch, tmp_path):
    path = tmp_path / "quoted' directory" / "result.json"
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "ResultPath": str(path.resolve()),
            "F314Sha256": "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11",
            "Scope": "historical self-restore only",
        }))

    monkeypatch.setattr(audit.subprocess, "run", run)
    assert audit.verify_recorded_bootbase_rehearsal(path)["verified"] is True
    argv, kwargs = calls[0]
    command = base64.b64decode(argv[-1]).decode("utf-16le")
    assert "Get-F319VerifiedRecoveryRehearsal -ResultPath" in command
    assert "quoted'' directory" in command
    assert "f319_recovery_guard.ps1" in command
    assert "-Execute" not in command and "Enter-F319HardwareGuard" not in command
    assert kwargs["stdin"] == audit.subprocess.DEVNULL
    assert kwargs["timeout"] == 45


@pytest.mark.parametrize("code,output", [
    (1, ""), (0, "not JSON"), (0, "{}"), (0, "null"),
    (0, json.dumps({"ResultPath": "different", "F314Sha256": "wrong"})),
])
def test_reader_errors_cannot_become_pass(monkeypatch, tmp_path, code, output):
    monkeypatch.setattr(audit.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code, stdout=output))
    assert audit.verify_recorded_bootbase_rehearsal(tmp_path / "result.json")["verified"] is False


@pytest.mark.parametrize("error", [OSError("missing PowerShell"), audit.subprocess.TimeoutExpired("proof", 45)])
def test_unavailable_reader_fails_closed(monkeypatch, tmp_path, error):
    def run(*args, **kwargs):
        raise error
    monkeypatch.setattr(audit.subprocess, "run", run)
    assert audit.verify_recorded_bootbase_rehearsal(tmp_path / "result.json")["verified"] is False
