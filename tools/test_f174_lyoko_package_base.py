from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f174_lyoko_package_base as f174  # noqa: E402


def test_built_package_base_contract() -> None:
    manifest_path = f174.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f174.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f174-lyoko-package-base/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    package = manifest["package_state"]["packages"][0]
    assert package["name"] == "lyoko-sysinfo"
    assert package["architecture"] == "arc700_uclibc_lyoko_v1"
    assert package["files"] == ["/usr/bin/lyoko-sysinfo"]
    inventory = manifest["foundation_assets"]["rootfs_diff"]
    changed_files = {
        path for path in inventory["changed_paths"]
        if inventory["new"][path]["type"] == "file"
    }
    assert changed_files == {
        "etc/lyoko/keys/feed-ed25519.pub",
        "etc/lyoko/package-abi",
        "etc/openmitrastar/release",
        "usr/bin/lyoko-sysinfo",
        "usr/share/lyoko/feed/Packages",
        "usr/share/lyoko/feed/Packages.sig.json",
        "usr/share/lyoko/packages/installed.json",
    }


def test_private_feed_key_is_not_packaged() -> None:
    if not f174.PACKAGE_OVERLAY.is_dir():
        return
    names = {path.name.lower() for path in f174.PACKAGE_OVERLAY.rglob("*") if path.is_file()}
    assert not any(name.endswith((".key", ".pem")) for name in names)
