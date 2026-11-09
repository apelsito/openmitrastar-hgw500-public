from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f187_session_ui as f187  # noqa: E402


def test_frozen_session_contract() -> None:
    overlay = f187.OVERLAY
    dashboard = (overlay / "www/dashboard.html").read_text(encoding="utf-8")
    login = (overlay / "www/login.html").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    cgi = (overlay / "usr/libexec/openmitrastar/om-oem-cgi").read_text(encoding="utf-8")
    assert 'href="/logout.cgi"' in dashboard
    assert 'action="/index.cgi"' in login
    assert 'type="password"' in login
    assert "lyoko.api.session/v1" in api
    assert 'cat "$web_root/login.html"' in cgi


def test_built_f187_contract() -> None:
    manifest_path = f187.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f187.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f187-session-ui/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "1.7.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-1.7-f187"
    assert manifest["frontend"]["asset_bytes"] < 64 * 1024
    assert len(manifest["frontend"]["login_html_sha256"]) == 64
    assert len(manifest["frontend"]["login_css_sha256"]) == 64
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert {"etc/lyoko/frontend.env", "etc/openmitrastar/release", "usr/libexec/openmitrastar/om-api-v1", "usr/libexec/openmitrastar/om-oem-cgi", "www/api/v1/session", "www/app.css", "www/app.js", "www/dashboard.html", "www/login.css", "www/login.html"} <= changed


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f187.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
