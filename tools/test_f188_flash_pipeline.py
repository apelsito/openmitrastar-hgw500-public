from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/build_flash_test_f188_diagnostics_ui.ps1"
GATE = ROOT / "tools/post_flash_f188_diagnostics_ui_gate.py"


def test_wrapper_is_guarded_and_targets_only_live_slot() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert 'target = "mtd4/linux_live"' in text
    assert "if (-not $Execute) { exit 0 }" in text
    assert "reboot_to_topaz_prompt_sysrq.ps1" in text
    assert "--transport uart-ymodem --uart-attach-topaz" in text
    assert "post_flash_f188_diagnostics_ui_gate.py" in text
    for forbidden in ("mtd3", "mtd5", "fw_setenv", "flash_erase"):
        assert forbidden not in text


def test_gate_checks_exact_frontend_identity_and_files() -> None:
    text = GATE.read_text(encoding="utf-8")
    for marker in (
        "lyoko-foundation-1.8-f188",
        "lyoko.api.frontend/v1",
        '"runtime": payload.get("runtime") == "router"',
        "sha256sum /www/dashboard.html /www/app.js /www/app.css /www/login.html /www/login.css",
        "post_flash_f179_integrated_gate.py",
        "lyoko.api.session/v1",
        "lyoko.api.diagnostics/v1",
        "rx_restart_total",
    ):
        assert marker in text


def test_wrapper_dry_run_reports_exact_candidate() -> None:
    proc = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(WRAPPER), "-SkipBuild",
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["target"] == "mtd4/linux_live"
    assert payload["bytes"] == 5_115_904
    assert payload["sha256"] == "aac1993994d6796b4a88caf1f5c21f601baec620b09b2c16c6dfa745c78a1f69"
