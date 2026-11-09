from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/salvage_f285_material_aelita_result.py"


def load_script():
    spec = importlib.util.spec_from_file_location("f285_salvage_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_client_passed_requires_real_5g_security_and_restore() -> None:
    module = load_script()
    oracle = {
        "execution_error": None,
        "test": {
            "connected": True,
            "ssid": module.TARGET_SSID,
            "band": "5 GHz",
            "channel": "36",
            "authentication": "WPA2-Personal",
            "cipher": "CCMP",
            "ipv4": "192.0.2.10",
            "router_ping": True,
        },
        "restore": {"connected": True},
        "profile_deleted": True,
        "secret_blob_deleted": True,
    }
    assert module.client_passed(oracle) is True
    oracle["test"]["cipher"] = "TKIP"
    assert module.client_passed(oracle) is False


def test_source_has_no_flash_or_sensitive_output_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"secrets_logged": False' in source
    assert '"client_macs_logged": False' in source
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source
