from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f179_integrated_napi_package_manager as f179  # noqa: E402


def test_integrated_artifact_uses_exact_parent_components() -> None:
    manifest_path = f179.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f172 = json.loads((f179.F172_BUILD / "manifest.json").read_text(encoding="ascii"))
    f177 = json.loads((f179.F177_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f179-integrated-napi-package-manager/v1"
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == f172["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["parents"]["f177_rootfs_sha256"] == f177["artifacts"]["rootfs_squashfs"]["sha256"]
    assert manifest["package_manager"] == f177["package_manager"]
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    changed = manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]
    assert changed == ["etc/openmitrastar/release"]


def test_storage_split_is_not_accidentally_enabled() -> None:
    manifest_path = f179.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["safety"]["storage_split"].startswith("not included")
