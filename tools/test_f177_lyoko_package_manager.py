from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f177_lyoko_package_manager as f177  # noqa: E402


def test_manager_source_is_volatile_and_offline() -> None:
    manager = (f177.FOUNDATION / "overlay/usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    assert "LYOKO_PKG_RUN_ROOT:-/run/lyoko-packages" in manager
    assert "feed_trust=immutable-build-verified" in manager
    assert "persistent_install=disabled" in manager
    assert "network_fetch=disabled" in manager
    assert "package-hash-mismatch" in manager
    assert "traversal-package-path" in manager
    for forbidden in ("/persist", "mtd", "wget", "curl", "opkg"):
        assert forbidden not in manager


def test_built_manager_contract() -> None:
    manifest_path = f177.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f177.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f177-lyoko-package-manager/v1"
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    manager = manifest["package_manager"]
    assert manager["key_id"] == "01ed300cc2b2a01d"
    assert manager["volatile_install_available"] is True
    assert manager["network_fetch"] is False
    assert manager["persistent_install"] is False
    assert {item["package"] for item in manager["bundled_packages"]} == {"lyoko-sysinfo", "lyoko-netdiag"}
    inventory = manifest["foundation_assets"]["rootfs_diff"]
    changed_files = {
        path for path in inventory["changed_paths"]
        if inventory["new"][path]["type"] == "file"
    }
    for required in (
        "usr/bin/lyoko-pkg",
        "usr/libexec/lyoko/pkgbox",
        "usr/share/lyoko/feed/archives/lyoko-netdiag_1.0.0-1_arc700_uclibc_lyoko_v1.ipk",
        "usr/share/lyoko/feed/archives/lyoko-sysinfo_1.0.0-1_arc700_uclibc_lyoko_v1.ipk",
    ):
        assert required in changed_files


def test_private_key_is_absent() -> None:
    if not f177.OVERLAY.is_dir():
        return
    names = {path.name.lower() for path in f177.OVERLAY.rglob("*") if path.is_file()}
    assert not any(name.endswith((".key", ".pem")) for name in names)
