from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f237_dual_radio_control_postflash_gate.ps1"


def test_f237_gate_is_dry_run_by_default_and_never_flashes() -> None:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["flash"] is False
    assert "OPENMITRASTAR_F237_DUAL_RADIO_CONTROL_PHYSICAL" in SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "nandwrite", "spi_flash", "fw_setenv", "COM3"):
        assert forbidden not in SCRIPT.read_text(encoding="utf-8")
