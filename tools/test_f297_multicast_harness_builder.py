from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-6.5.4-f297-multicast-harness"
OVERLAY = FOUNDATION / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F296 = PRIVATE / "f296-device-bound"
F297 = PRIVATE / "f297-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ui_keeps_hardware_rx_and_store_protection() -> None:
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


def test_multicast_harness_is_guarded_and_nonpersistent() -> None:
    feature = (OVERLAY / "etc/openmitrastar/features/multicast-cert-v1").read_text(encoding="ascii")
    backend = (OVERLAY / "usr/sbin/om-multicast-cert").read_text(encoding="utf-8")
    assert feature.strip() == "OPENMITRASTAR_MULTICAST_CERT=1"
    for marker in (
        "OPENMITRASTAR_MULTICAST_CERT_V1",
        "rollback-watchdog",
        "acquire_lock",
        "restore_values",
        "multicast_snooping",
        "multicast_querier",
        "multicast_router",
    ):
        assert marker in backend
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/persist", "/dev/mtd"):
        assert forbidden not in backend


def test_observer_remains_packaged_but_has_no_autoload_path() -> None:
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


def test_f297_manifest_is_disabled_offline_hold() -> None:
    manifest = json.loads((F297 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f297-multicast-harness-from-f296/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["developer_console"]["emac_diagnostics"] == "interactive hardware RX-demand inspector"
    assert manifest["developer_console"]["store_protection"] == "read-only observer status"
    assert manifest["multicast_certification"]["enabled_at_boot"] is False
    assert manifest["multicast_certification"]["feature_available"] is True
    assert manifest["multicast_certification"]["persistent_writes"] is False
    assert manifest["multicast_certification"]["hardware_status"] == "NOT_RUN"
    assert manifest["store_protection_observer"]["autoload"] is False
    assert manifest["store_protection_observer"]["feature_default"] is False
    assert manifest["store_protection_observer"]["read_commands_only"] is True
    assert manifest["store_protection_observer"]["program"] is False
    assert manifest["store_protection_observer"]["erase"] is False
    source_manifest = json.loads((F296 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["store_protection_observer"] == source_manifest["store_protection_observer"]
    assert manifest["native_qtn_control"] == source_manifest["native_qtn_control"]
    assert manifest["native_rtl_control"] == source_manifest["native_rtl_control"]
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "etc/openmitrastar/features/multicast-cert-v1",
        "usr/sbin/om-multicast-cert",
        "usr/share/openmitrastar/web/dashboard.html",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F297 / named("f297", suffix)) == sha256(F296 / named("f296", suffix))
