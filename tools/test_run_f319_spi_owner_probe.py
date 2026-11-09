from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f319_spi_owner_probe.ps1"


def test_source_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'OPENMITRASTAR_F319_SPI_OWNER_CLAIM_E33D8511' in source
    assert 'qtn-topaz-spi-owner-probe.ko' in source
    assert 'controller_read_count' in source
    assert 'controller_write_count' in source
    assert 'transaction_provider_ready' in source
    assert 'OMF319_SPI_OWNER_PASS' in source
    assert 'StrictHostKeyChecking=yes' in source
    assert 'Start-Process -FilePath "powershell.exe" -WindowStyle Hidden' in source
    assert 'Assert-F319UartBinding' in source
    assert 'ExpectedPnpDeviceId' in source
    assert 'Wait-F319UartCaptureReady' in source
    assert '-ExternalOwnershipHeld' in source
    assert source.index('Assert-F319UartBinding') < source.index('insmod "$module"')
    assert source.index('Wait-F319UartCaptureReady') < source.index('insmod "$module"')
    assert 'flash_erase' not in source
    assert 'mtd_debug' not in source
    assert 'nandwrite' not in source
    assert 'fw_setenv' not in source


def test_dry_run() -> None:
    with tempfile.TemporaryDirectory(prefix="f319-runtime-probe-") as directory:
        output = Path(directory) / "evidence"
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(SCRIPT), "-OutputDir", str(output),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        plan = json.loads((output / "plan.json").read_text(encoding="utf-8-sig"))
        assert plan["mode"] == "dry-run"
        assert plan["local_preflight_pass"] is True
        assert plan["hardware_actions_performed"] is False
        assert plan["forbidden_actions"] == ["flash", "MTD write", "SPI opcode", "radio mutation", "reboot"]
