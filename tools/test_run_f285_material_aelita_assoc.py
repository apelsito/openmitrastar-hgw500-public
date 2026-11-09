from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f285_material_aelita_assoc.py"


def load_script():
    spec = importlib.util.spec_from_file_location("f285_assoc", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dry_run_describes_secure_client_gate() -> None:
    proc = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "openmitrastar.f285-material-aelita-plan/v1"
    assert payload["target_ssid"] == "Lyoko-5G-Material-Test"
    assert payload["restore_ssid"] == "MOVISTAR-WIFI6-A348"
    assert payload["router_watchdog"] is True
    assert payload["client_restore_watchdog"] is True
    assert payload["flash"] is False and payload["mtd_writes"] is False


def test_source_never_logs_secret_or_client_mac() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'psk = ""' in source
    assert '"secrets_logged": False' in source
    assert '"client_macs_logged": False' in source
    assert "ap_bssid" not in source
    assert '"raw"' not in source
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source


def test_compact_oracle_prefers_connected_l3_snapshot() -> None:
    module = load_script()
    payload = {
        "schema": "oracle/v1",
        "restore_ssid": "RESTORE",
        "execution_error": None,
        "profile_deleted": True,
        "secret_blob_deleted": True,
        "test": {
            "connected": True,
            "wlan_before_download": {"estado": "desconectado"},
            "ipv4": {"ipv4": "192.0.2.10", "gateway": "192.0.2.1"},
            "router_ping": {"pass": True},
            "l3_diagnostics_after_ping": {
                "wifi": {
                    "estado": "conectado",
                    "ssid": module.TARGET_SSID,
                    "banda": "5 GHz",
                    "canal": "36",
                    "tipo_de_radio": "802.11ac",
                    "autenticaci_n": "WPA2-Personal",
                    "cifrado": "CCMP",
                    "velocidad_de_recepci_n_mbps": "866.7",
                    "velocidad_de_transmisi_n_mbps": "866.7",
                    "se_al": "93%",
                    "rssi": "-29",
                }
            },
        },
        "restore": {"connected": True, "error": None},
    }
    compact = module.compact_oracle(payload)
    assert compact["test"]["ssid"] == module.TARGET_SSID
    assert compact["test"]["band"] == "5 GHz"
    assert compact["test"]["channel"] == "36"
    assert compact["test"]["authentication"] == "WPA2-Personal"
    assert compact["test"]["cipher"] == "CCMP"
    assert compact["restore"]["ssid"] == "RESTORE"
