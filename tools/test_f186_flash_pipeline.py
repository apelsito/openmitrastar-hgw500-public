from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/build_flash_test_f186_navigation_shell.ps1"
GATE = ROOT / "tools/post_flash_f186_navigation_shell_gate.py"


def test_wrapper_is_guarded_and_targets_only_live_slot() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert 'target = "mtd4/linux_live"' in text
    assert "if (-not $Execute) { exit 0 }" in text
    assert "reboot_to_topaz_prompt_sysrq.ps1" in text
    assert "--transport uart-ymodem --uart-attach-topaz" in text
    assert "post_flash_f186_navigation_shell_gate.py" in text
    for forbidden in ("mtd3", "mtd5", "fw_setenv", "flash_erase"):
        assert forbidden not in text


def test_gate_checks_exact_frontend_identity_and_files() -> None:
    text = GATE.read_text(encoding="utf-8")
    for marker in (
        "lyoko-foundation-1.6-f186",
        "lyoko.api.frontend/v1",
        '"runtime": payload.get("runtime") == "router"',
        "sha256sum /www/dashboard.html /www/app.js /www/app.css",
        "post_flash_f179_integrated_gate.py",
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
    assert payload["sha256"] == "d4fe00a9dca9868251ea4e2964ee98349fb81ab6280d036141454af566191ca1"
