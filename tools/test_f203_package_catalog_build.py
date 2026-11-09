from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f203_package_catalog as f203  # noqa: E402


def test_frozen_package_catalog() -> None:
    overlay = f203.OVERLAY
    manager = (overlay / "usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    for marker in ("search)", "info)", "depends)", "plan)", "update)", "dependency-cycle", "package-required", "max_dependency_depth"):
        assert marker in manager
    assert '"dependency_resolution":"exact-name-only"' in api
    assert '"available_count"' in api


def test_built_f203_contract() -> None:
    manifest_path = f203.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f203.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f203-package-catalog/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.7.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.7-f203"
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/bin/lyoko-pkg" in changed
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f203.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
