from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import build_f309_authenticated_dashboard_from_f306 as builder


DEVICE = "hgw500bna-qcv2-a2-primary"
PRIVATE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F306 = PRIVATE / "f306-device-bound"
F309 = PRIVATE / "f309-device-bound"
OVERLAY = builder.FOUNDATION_SOURCE


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="ascii"))


def env(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="ascii").splitlines() if "=" in line)


@pytest.fixture(scope="session")
def roots() -> dict[str, Path]:
    root = builder.ROOT / ".codex_tmp/test-f309-auth-rootfs"
    if root.exists():
        resolved = root.resolve()
        assert resolved == (builder.ROOT / ".codex_tmp/test-f309-auth-rootfs").resolve()
        shutil.rmtree(resolved)
    old = root / "f306"
    new = root / "f309"
    root.mkdir(parents=True)
    builder.f306.extract_rootfs(F306 / named("f306", ".rootfs.squashfs"), old, "podman-mem9-tidb")
    builder.f306.extract_rootfs(F309 / named("f309", ".rootfs.squashfs"), new, "podman-mem9-tidb")
    yield {"f306": old, "f309": new}
    if root.exists():
        shutil.rmtree(root.resolve())


def test_source_overlay_is_exact_and_excludes_public_dashboard() -> None:
    actual = {path.relative_to(OVERLAY).as_posix() for path in OVERLAY.rglob("*") if path.is_file()}
    assert actual == builder.SOURCE_OVERLAY_FILES
    assert "www/dashboard.html" not in actual
    builder.validate_source_overlay()


def test_manifest_is_rootfs_only_flash_candidate() -> None:
    data = manifest(F309)
    assert data["schema"] == "openmitrastar.f309-authenticated-dashboard-candidate/v1"
    assert data["classification"] == "PRIVATE_DEVICE_BOUND_MTD4_AUTHENTICATION_FIX_CANDIDATE"
    assert data["candidate_eligible"] is True
    assert data["release_eligible"] is False
    assert data["flash_supported"] is True
    assert data["physical_validation"]["status"] == "NOT_RUN"
    assert data["web_security"]["legacy_dashboard_removed"] is True
    assert data["web_security"]["public_dashboard_html"] is False


def test_kernel_config_dtb_and_vmlinux_are_exact_f306() -> None:
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F309 / named("f309", suffix)) == sha256(F306 / named("f306", suffix))


def test_rootfs_diff_is_exact_and_public_dashboard_absent(roots: dict[str, Path]) -> None:
    data = manifest(F309)
    assert set(data["foundation_assets"]["rootfs_diff"]["changed_paths"]) == builder.EXPECTED_ROOTFS_CHANGES
    assert not (roots["f309"] / "www/dashboard.html").exists()
    assert (roots["f309"] / "usr/share/openmitrastar/web/dashboard.html").is_file()
    assert "6.7.4-f309" in (roots["f309"] / "usr/share/openmitrastar/web/dashboard.html").read_text(encoding="utf-8")


def test_login_cgi_api_and_credentials_are_byte_identical_to_f306(roots: dict[str, Path]) -> None:
    for relative in (
        "usr/libexec/openmitrastar/om-oem-cgi",
        "usr/libexec/openmitrastar/om-api-v1",
        "www/dashboard.cgi",
        "www/index.cgi",
        "www/login.html",
        "www/login.css",
    ):
        assert sha256(roots["f309"] / relative) == sha256(roots["f306"] / relative)
    old_manifest = manifest(F306)
    new_manifest = manifest(F309)
    assert new_manifest["device_identity"] == old_manifest["device_identity"]
    assert new_manifest["web_identity"] == old_manifest["web_identity"]
    cgi = (roots["f309"] / "usr/libexec/openmitrastar/om-oem-cgi").read_text(encoding="utf-8")
    assert "require_page_session || exit 0; render_management_page" in cgi
    assert "cat /usr/share/openmitrastar/web/dashboard.html" in cgi


def test_frontend_identity_and_asset_hashes_are_coherent(roots: dict[str, Path]) -> None:
    root = roots["f309"]
    release = env(root / "etc/openmitrastar/release")
    frontend = env(root / "etc/lyoko/frontend.env")
    assert release["OPENMITRASTAR_PRODUCT_VERSION"] == builder.PRODUCT_VERSION
    assert release["OPENMITRASTAR_UI_VERSION"] == builder.UI_VERSION
    assert frontend["LYOKO_UI_VERSION"] == builder.UI_VERSION
    assert frontend["LYOKO_UI_SOURCE"] == builder.UI_SOURCE
    total = 0
    for key, relative in builder.FRONTEND_ASSETS.items():
        assert frontend[key] == sha256(root / relative)
        total += (root / relative).stat().st_size
    assert int(frontend["LYOKO_UI_ASSET_BYTES"]) == total


def test_all_86_radio_files_are_byte_identical_to_f306(roots: dict[str, Path]) -> None:
    old = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f306"], "podman-mem9-tidb")))
    new = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f309"], "podman-mem9-tidb")))
    assert len(old) == 86
    assert new == old
    data = manifest(F309)
    assert data["integration"]["radio_payload_file_count"] == 86
    assert data["integration"]["radio_payload_byte_identical_to_f306"] is True
    assert data["integration"]["reproducible_two_builds"] is True


def test_unchanged_public_assets_remain_exact_f306(roots: dict[str, Path]) -> None:
    for relative in (
        "www/app.js", "www/app.css", "www/capabilities.css", "www/layout-fixes.css",
        "www/assets/logo.svg", "www/assets/movistar-logo.svg", "www/assets/movistar-m.png",
        "www/assets/router-label-help-sanitized.jpg", "www/assets/telefonica-logo.svg",
    ):
        assert sha256(roots["f309"] / relative) == sha256(roots["f306"] / relative)


def test_candidate_layout_slot_fit_and_store_boundary() -> None:
    data = manifest(F309)
    candidate = F309 / data["artifacts"]["webformat"]["file"]
    rootfs = F309 / named("f309", ".rootfs.squashfs")
    payload = candidate.read_bytes()
    assert candidate.stat().st_size == data["artifacts"]["webformat"]["bytes"]
    assert sha256(candidate) == data["artifacts"]["webformat"]["sha256"]
    assert payload[builder.f306.ROOTFS_OFFSET:] == rootfs.read_bytes()
    assert payload[builder.f306.ROOTFS_OFFSET:builder.f306.ROOTFS_OFFSET + 4] == b"hsqs"
    assert len(payload) <= builder.f306.STORE_SLOT_OFFSET
    assert data["storage"]["store_erased_ff"] is True


def test_sha256sums_cover_every_packaged_artifact() -> None:
    sums = {}
    for line in (F309 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    actual = {path.name: sha256(path) for path in F309.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    assert sums == actual
