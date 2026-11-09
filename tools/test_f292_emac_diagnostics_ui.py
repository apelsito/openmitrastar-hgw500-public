from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-6.5.0-f292-emac-diagnostics-ui"
OVERLAY = FOUNDATION / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F290 = PRIVATE / "f290-device-bound"
F292 = PRIVATE / "f292-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_diagnostics_ui_exposes_causal_metrics() -> None:
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    css = (OVERLAY / "www/app.css").read_text(encoding="utf-8")
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    emulator = (FOUNDATION / "emulator/server.py").read_text(encoding="utf-8")
    for marker in ("diagnostic-workspace", "diagnostic-help-title", "diagnostic-help-rule", "diagnostic-help-state"):
        assert marker in html
    for marker in ("diagnosticHelp", "rx_fault_observations", "last_rx_fault_status", "rx_restart_last_fault_age_ms", "Recuperación RX causada"):
        assert marker in js
    for marker in (".diagnostic-workspace", ".diagnostic-help", ".diagnostic-metric.active"):
        assert marker in css
    for marker in ("rx_fault_observations", "last_rx_fault_status", "rx_restart_last_fault_age_ms"):
        assert marker in emulator
    syntax = subprocess.run(["node", "--check", str(OVERLAY / "www/app.js")], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr


def test_f292_manifest_is_rootfs_only() -> None:
    manifest = json.loads((F292 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f292-emac-diagnostics-ui/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["developer_console"]["emac_diagnostics"] == "interactive causal restart inspector"
    source_manifest = json.loads((F290 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["native_qtn_control"] == source_manifest["native_qtn_control"]
    assert manifest["native_rtl_control"] == source_manifest["native_rtl_control"]
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/share/openmitrastar/web/dashboard.html",
        "www/app.css",
        "www/app.js",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F292 / named("f292", suffix)) == sha256(F290 / named("f290", suffix))
