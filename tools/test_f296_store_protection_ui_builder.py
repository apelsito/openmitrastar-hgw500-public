from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-6.5.3-f296-store-protection-ui"
OVERLAY = FOUNDATION / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F294 = PRIVATE / "f294-device-bound"
F296 = PRIVATE / "f296-device-bound"
MODULE = ROOT / "outputs/kernel-port/f295-store-protection-observer-20260904/qtn-topaz-store-protection-observer.ko"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ui_exposes_hardware_rx_and_store_protection() -> None:
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    css = (OVERLAY / "www/app.css").read_text(encoding="utf-8")
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    emulator = (FOUNDATION / "emulator/server.py").read_text(encoding="utf-8")
    for marker in ("rx-path", "diagnostic-workspace", "diagnostic-help-title", "diagnostic-help-rule", "diagnostic-help-state"):
        assert marker in html
    for marker in ("diagnosticHelp", "renderRxPath", "mac_rx_frames", "dma_missed_frames_total", "rx_restart_last_mac_rx_progress_age_ms", "Bloqueo RX con tráfico físico"):
        assert marker in js
    for marker in (".rx-path", ".rx-stage.bad", ".diagnostic-workspace", ".diagnostic-help", ".diagnostic-metric.active"):
        assert marker in css
    for marker in ("mac_rx_frames_valid", "mac_rx_frames", "dma_missed_frames_total", "rx_restart_last_mac_rx_progress_age_ms"):
        assert marker in emulator
    for marker in ("protection_probe", "Observador de protección", "Protección por bloque", "Control SPI restaurado"):
        assert marker in js or marker in emulator
    api = (OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    for marker in ("store_protection_root", "store-protection-observer-v1", "read_commands_only", "write_capable"):
        assert marker in api
    assert "insmod" not in api


def test_observer_is_packaged_but_has_no_autoload_path() -> None:
    feature = (OVERLAY / "etc/openmitrastar/features/store-protection-observer-v1").read_text(encoding="ascii")
    assert "OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0" in feature
    assert "OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0" in feature
    assert "OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0" in feature
    init_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (OVERLAY / "etc/init.d").iterdir()
        if path.is_file()
    )
    assert "qtn-topaz-store-protection-observer" not in init_text
    syntax = subprocess.run(["node", "--check", str(OVERLAY / "www/app.js")], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr


def test_f296_manifest_is_disabled_offline_hold() -> None:
    manifest = json.loads((F296 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f296-store-protection-ui-from-f294/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["developer_console"]["emac_diagnostics"] == "interactive hardware RX-demand inspector"
    assert manifest["developer_console"]["store_protection"] == "read-only observer status"
    assert manifest["store_protection_observer"]["autoload"] is False
    assert manifest["store_protection_observer"]["feature_default"] is False
    assert manifest["store_protection_observer"]["read_commands_only"] is True
    assert manifest["store_protection_observer"]["program"] is False
    assert manifest["store_protection_observer"]["erase"] is False
    assert manifest["store_protection_observer"]["sha256"] == sha256(MODULE)
    source_manifest = json.loads((F294 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["native_qtn_control"] == source_manifest["native_qtn_control"]
    assert manifest["native_rtl_control"] == source_manifest["native_rtl_control"]
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "etc/openmitrastar/features/store-protection-observer-v1",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-protection-observer.ko",
        "usr/libexec/openmitrastar/om-api-v1",
        "usr/share/openmitrastar/web/dashboard.html",
        "www/app.css",
        "www/app.js",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F296 / named("f296", suffix)) == sha256(F294 / named("f294", suffix))
