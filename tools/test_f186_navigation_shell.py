from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f186_navigation_shell as f186  # noqa: E402


def test_frozen_navigation_contract() -> None:
    html = (f186.OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    js = (f186.OVERLAY / "www/app.js").read_text(encoding="utf-8")
    for page in ("home", "network", "wifi", "system", "diagnostics"):
        assert f'data-page-panel="{page}"' in html
    for mode in ("normal", "advanced", "developer"):
        assert f'data-mode="{mode}"' in html
    assert "Promise.allSettled" in js
    assert "changedRadioValues" in js
    assert "nav-open" in js


def test_built_f186_contract() -> None:
    manifest_path = f186.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f186.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f186-navigation-shell/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "1.6.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-1.6-f186"
    assert manifest["frontend"]["asset_bytes"] < 64 * 1024
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert {"etc/lyoko/frontend.env", "etc/openmitrastar/release", "www/app.css", "www/app.js", "www/dashboard.html"} <= changed


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f186.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
