from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f197_common_radio_contract as f197  # noqa: E402


def test_frozen_common_radio_contract() -> None:
    overlay = f197.OVERLAY
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    radioctl = (overlay / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    assert "OM_RADIOCTL" in api
    for direct_backend in ("OM_HOSTAPD_CLI", "OM_QTN_HOSTAPD_CLI", "OM_IWCONFIG_QTN", "OM_IWPRIV_QTN"):
        assert direct_backend not in api
    for operation in (
        "identity", "capabilities", "status", "snapshot", "clients",
        "stage_config", "apply_config", "rollback_config", "restart_radio",
    ):
        assert f"{operation})" in radioctl
    assert '"restart_radio":false' in radioctl
    assert "scoped-recovery-not-certified" in radioctl


def test_built_f197_contract() -> None:
    manifest_path = f197.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f197.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f197-common-radio-contract/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.4.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.4-f197"
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/sbin/om-radioctl" in changed
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert manifest["foundation_assets"]["removed_paths"] == []
    assert manifest["promotion_recommendation"].startswith("HOLD_")
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f197.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
