from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f173_lyoko_hardware_inventory as f173  # noqa: E402


def test_source_contract_is_read_only_and_complete() -> None:
    api = (f173.OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    for name in (
        "OpenMitraStar Wi-Fi button",
        "OpenMitraStar 5 GHz button",
        "OpenMitraStar reset button",
        "openmitrastar:green:wlan2g",
        "openmitrastar:green:wlan5g",
        "openmitrastar:panel:signalb",
        "openmitrastar:panel:signalg",
        "openmitrastar:panel:signalr",
        "topaz:stage0:alive",
    ):
        assert name in api
    assert '"available":false' in api
    assert '"present":false' in api
    hardware = api[api.index("hardware)"):api.index("diagnostics)")]
    for forbidden in (">brightness", "echo 1", "echo 0", "gpio_set", "reboot", "mtd"):
        assert forbidden not in hardware


def test_built_artifact_contract() -> None:
    manifest_path = f173.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f173.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f173-lyoko-hardware-inventory/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert changed == {
        "etc/openmitrastar/release",
        "usr/libexec/openmitrastar/om-api-v1",
        "www/app.js",
        "www/dashboard.html",
    }


def test_dev_ui_contract() -> None:
    app = (f173.OVERLAY / "www/app.js").read_text(encoding="utf-8")
    assert "Botones registrados" in app
    assert "LEDs controlables" in app
    assert "hardware.watchdog.present" in app
