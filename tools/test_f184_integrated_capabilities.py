from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f184_integrated_capabilities as f184  # noqa: E402


def test_f184_uses_exact_kernel_and_rootfs_parents() -> None:
    manifest_path = f184.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f172 = json.loads((f184.F172_BUILD / "manifest.json").read_text(encoding="ascii"))
    f183 = json.loads((f184.F183_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f184-integrated-capabilities/v1"
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == f172["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["parents"]["f183_rootfs_sha256"] == f183["artifacts"]["rootfs_squashfs"]["sha256"]
    assert manifest["capability_registry"]["items"] == 16
    assert manifest["package_manager"] == f183["package_manager"]
    assert manifest["foundation_assets"]["rootfs_diff"]["changed_paths"] == ["etc/openmitrastar/release"]


def test_f184_keeps_storage_split_out() -> None:
    manifest_path = f184.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["safety"]["storage_split"] == "not included"
