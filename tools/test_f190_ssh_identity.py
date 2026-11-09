from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f190_ssh_identity as f190  # noqa: E402


def test_frozen_ssh_identity_contract() -> None:
    overlay = f190.OVERLAY
    ssh = (overlay / "usr/sbin/om-ssh").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    assert not (overlay / f190.EMBEDDED_HOST_KEY).exists()
    assert "factory_host_key" not in ssh
    assert "identity_persistence=ephemeral" in ssh
    assert "host-key-validation" in ssh
    assert "lyoko.api.ssh/v1" in api
    assert '"private"' not in api


def test_built_f190_contract() -> None:
    manifest_path = f190.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f190.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f190-ssh-identity/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "1.9.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-1.9-f190"
    assert manifest["frontend"]["asset_bytes"] < 64 * 1024
    assert len(manifest["frontend"]["login_html_sha256"]) == 64
    assert len(manifest["frontend"]["login_css_sha256"]) == 64
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert f190.EMBEDDED_HOST_KEY in changed
    assert manifest["foundation_assets"]["rootfs_diff"]["new"][f190.EMBEDDED_HOST_KEY] is None
    assert manifest["foundation_assets"]["removed_paths"] == [f190.EMBEDDED_HOST_KEY]
    assert manifest["promotion_recommendation"].startswith("HOLD_")
    assert {"etc/lyoko/frontend.env", "etc/openmitrastar/release", "usr/libexec/openmitrastar/om-api-v1", "usr/sbin/om-ssh", "www/api/v1/ssh", "www/app.js", "www/dashboard.html"} <= changed


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f190.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
