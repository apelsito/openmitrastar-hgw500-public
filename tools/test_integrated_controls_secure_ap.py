#!/usr/bin/env python3
"""Offline safety contract for the integrated RAM-only orchestrator."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_openmitrastar_integrated_controls_secure_ap.ps1"
IMAGE = ROOT / "work/tftp/omvl/linux510-radiohw-controls-integrated-RAM-ONLY.bin"
EXPECTED = "9bbd30181b0df52e5c2b982dd3b767c0cc00657cdb13dd12d097f52468ab2913"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)


text = SCRIPT.read_text(encoding="utf-8")
assert hashlib.sha256(IMAGE.read_bytes()).hexdigest() == EXPECTED
assert "OPENMITRASTAR_INTEGRATED_CONTROLS_RAM_ONLY" in text
assert "-skip-boot" in text.lower()
assert "run_openmitrastar_ap_detached.ps1" in text
assert "openmitrastar:green:wlan2g/brightness" in text
assert "OpenMitraStar Wi-Fi button" in text
for forbidden in ("flash_erase", "flashcp", "mtd_debug", "flash_image_update"):
    assert forbidden not in text

dry = run(
    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", str(SCRIPT),
)
assert dry.returncode == 0, dry.stderr
assert "OMINTEGRATED_DRY_RUN_PASS=1" in dry.stdout
assert '"flash_supported":  false' in dry.stdout

refused = run(
    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", str(SCRIPT), "-ExecuteRam",
)
assert refused.returncode != 0
assert "Execution requires exact -AckRamOnly" in (refused.stdout + refused.stderr)

print("OMINTEGRATED_TEST_PASS hash=1 dry_run=1 missing_ack=refused flash_primitives=absent")
