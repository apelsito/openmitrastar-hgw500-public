from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f188_diagnostics_ui as f188  # noqa: E402


def test_frozen_diagnostics_contract() -> None:
    overlay = f188.OVERLAY
    dashboard = (overlay / "www/dashboard.html").read_text(encoding="utf-8")
    js = (overlay / "www/app.js").read_text(encoding="utf-8")
    css = (overlay / "www/app.css").read_text(encoding="utf-8")
    assert 'id="diagnostics-health"' in dashboard
    assert 'id="diagnostics-raw"' in dashboard
    for marker in ("renderDiagnostics", "NO_RX_DESC", "Sin nuevos stalls", "previousDiagnostics"):
        assert marker in js
    assert ".diagnostic-grid" in css


def test_built_f188_contract() -> None:
    manifest_path = f188.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f188.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f188-diagnostics-ui/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "1.8.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-1.8-f188"
    assert manifest["frontend"]["asset_bytes"] < 64 * 1024
    assert len(manifest["frontend"]["login_html_sha256"]) == 64
    assert len(manifest["frontend"]["login_css_sha256"]) == 64
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert {"etc/lyoko/frontend.env", "etc/openmitrastar/release", "www/app.css", "www/app.js", "www/dashboard.html", "www/login.html"} <= changed


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f188.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
