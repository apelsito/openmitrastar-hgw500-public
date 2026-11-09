from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_aelita_testbench_recovery_bundle.ps1"
BUNDLE = ROOT / "outputs/aelita-testbench/lyoko-aelita-testbench-recovery-20260902"


def test_builder_creates_public_only_bundle() -> None:
    result = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["contains_private_keys"] is False
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="ascii"))
    assert manifest["contains_private_keys"] is False
    names = {item["file"] for item in manifest["files"]}
    assert names == {"README.txt", "oracle_ed25519.pub", "repair_aelita_testbench.ps1"}
    assert not any("private" in name.lower() for name in names)


def test_bundle_build_is_reproducible() -> None:
    first = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    second = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout)["sha256"] == json.loads(second.stdout)["sha256"]


def test_builder_is_scoped_to_output_directory() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "outputs\\aelita-testbench" in source
    assert "StartsWith" in source
    for forbidden in ("Remove-Item -Recurse", "Format-Volume", "Clear-Disk", "Restart-Computer"):
        assert forbidden not in source
