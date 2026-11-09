from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/prepare_f194_recovery_provisioning.py"


def test_contract_is_complete_and_non_executing() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "contract.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--output", str(output)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        contract = json.loads(output.read_text(encoding="ascii"))
        assert contract["status"] == "WAITING_EXPLICIT_EXCEPTION_AUTHORIZATION"
        assert contract["authorization"]["granted"] is False
        assert contract["target"]["partition"] == "mtd3/linux_safety"
        assert contract["target"]["offset"] == "0x00040000"
        assert contract["target"]["slot_bytes"] == 0x7A0000
        assert len(contract["target"]["full_slot_sha256"]) == 64
        assert all(contract["checks"].values())
        assert all(value is False for value in contract["hardware_actions_performed"].values())
        assert contract["decision"] == "NO_EXECUTOR_EMITTED_UNTIL_EXPLICIT_AUTHORIZATION"


def test_source_contains_no_hardware_executor() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "spi_flash write", "mtd_debug", "fw_setenv", "saveenv", "COM3", "serial.Serial"):
        assert forbidden not in source
