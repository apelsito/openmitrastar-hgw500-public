from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f192_ipv6_health_reconcile as f192  # noqa: E402


def test_frozen_ipv6_health_contract() -> None:
    overlay = f192.OVERLAY
    policy = (overlay / "usr/sbin/om-ipv6-local-policy").read_text(encoding="utf-8")
    ready = (overlay / "etc/init.d/S90-ready").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    assert "OM_IPV6_WAIT_SECONDS" in policy
    assert 'ipv6_attempt" -lt 3' in ready
    assert "degraded_services_json" in api
    assert '"degraded_services"' in api


def test_built_f192_contract() -> None:
    manifest_path = f192.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f192.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f192-ipv6-health-reconcile/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.1.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.1-f192"
    assert manifest["frontend"]["asset_bytes"] < 64 * 1024
    assert len(manifest["frontend"]["login_html_sha256"]) == 64
    assert len(manifest["frontend"]["login_css_sha256"]) == 64
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/sbin/om-ipv6-local-policy" in changed
    assert "etc/init.d/S90-ready" in changed
    assert manifest["foundation_assets"]["removed_paths"] == []
    assert manifest["promotion_recommendation"].startswith("HOLD_")
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"
    assert {"etc/init.d/S90-ready", "etc/lyoko/frontend.env", "etc/openmitrastar/release", "usr/libexec/openmitrastar/om-api-v1", "usr/sbin/om-ipv6-local-policy", "www/app.js", "www/dashboard.html"} <= changed


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f192.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
