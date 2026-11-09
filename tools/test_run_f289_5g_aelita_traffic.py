from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f289_5g_aelita_traffic.py"


def load_script():
    spec = importlib.util.spec_from_file_location("f289_5g_traffic_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dry_run_contract() -> None:
    proc = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["ssid"] == "MOVISTAR_PLUS_55CB"
    assert plan["firmware"] == "lyoko-foundation-6.4.2-f289-emac-fault-only-restart-device"
    assert plan["transfers"]["download_bytes"] == 32 * 1024 * 1024
    assert plan["transfers"]["upload_bytes"] == 32 * 1024 * 1024
    assert plan["soak_seconds"] == 120
    assert plan["router_mutations"] is False
    assert plan["flash"] is False and plan["mtd_writes"] is False


def test_transfer_view_and_source_safety() -> None:
    module = load_script()
    view = module.transfer_view({"pass": True, "bytes": 33554432, "seconds": 8, "speed_Bps": 4194304})
    assert view == {"pass": True, "bytes": 33554432, "seconds": 8.0, "mbps": 33.554}
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"secrets_logged": False' in source
    assert '"client_macs_logged": False' in source
    assert "wait_client_restore" in source
    assert "--reconcile-existing" in source
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source
