from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f201_radio_contract_ui as f201  # noqa: E402


def test_frozen_radio_contract_ui() -> None:
    overlay = f201.OVERLAY
    radioctl = (overlay / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    frontend = (overlay / "www/app.js").read_text(encoding="utf-8")
    html = (overlay / "www/dashboard.html").read_text(encoding="utf-8")
    assert "contract)" in radioctl
    assert "view=contract" in api
    assert "/api/v1/radios/2g?view=contract" in frontend
    assert "/api/v1/radios/5g?view=contract" in frontend
    assert 'id="radio2-contract"' in html and 'id="radio5-contract"' in html


def test_built_f201_contract() -> None:
    manifest_path = f201.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f201.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f201-radio-contract-ui/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.6.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.6-f201"
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/sbin/om-radioctl" in changed
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert "www/app.js" in changed
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f201.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
