from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f195_package_hardening as f195  # noqa: E402


def test_frozen_package_hardening_contract() -> None:
    overlay = f195.OVERLAY
    manager = (overlay / "usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    for marker in ("validate_data_archive", "unsupported-package-entry", "duplicate-package-path", "package-activate-failed", "runtime_signature_verification=disabled"):
        assert marker in manager
    assert '"verification_scope":"build-time"' in api
    assert '"runtime_integrity":"sha256-pinned"' in api


def test_built_f195_contract() -> None:
    manifest_path = f195.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f195.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f195-package-hardening/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.3.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.3-f195"
    assert manifest["frontend"]["asset_bytes"] < 64 * 1024
    assert len(manifest["frontend"]["login_html_sha256"]) == 64
    assert len(manifest["frontend"]["login_css_sha256"]) == 64
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/bin/lyoko-pkg" in changed
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert manifest["foundation_assets"]["removed_paths"] == []
    assert manifest["promotion_recommendation"].startswith("HOLD_")
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"
    assert {"etc/lyoko/frontend.env", "etc/openmitrastar/release", "usr/bin/lyoko-pkg", "usr/libexec/openmitrastar/om-api-v1", "www/app.js", "www/dashboard.html"} <= changed


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f195.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
