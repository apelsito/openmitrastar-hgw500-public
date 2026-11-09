from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

import build_f310_canonical_frontend_identity_from_f309 as builder


DEVICE = "hgw500bna-qcv2-a2-primary"
PRIVATE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F309 = PRIVATE / "f309-device-bound"
F310 = PRIVATE / "f310-device-bound"
OVERLAY = builder.FOUNDATION_SOURCE
ROOT = builder.ROOT
BUSYBOX = ROOT / "tools/external/llvm-mingw-20260616-ucrt-x86_64/busybox/bin/busybox.exe"


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
    root = builder.ROOT / ".codex_tmp/test-f310-identity-rootfs"
    if root.exists():
        resolved = root.resolve()
        assert resolved == (builder.ROOT / ".codex_tmp/test-f310-identity-rootfs").resolve()
        shutil.rmtree(resolved)
    old = root / "f309"
    new = root / "f310"
    root.mkdir(parents=True)
    builder.f306.extract_rootfs(F309 / named("f309", ".rootfs.squashfs"), old, "podman-mem9-tidb")
    builder.f306.extract_rootfs(F310 / named("f310", ".rootfs.squashfs"), new, "podman-mem9-tidb")
    yield {"f309": old, "f310": new}
    if root.exists():
        shutil.rmtree(root.resolve())


def test_source_overlay_is_minimal_and_lf_only() -> None:
    actual = {path.relative_to(OVERLAY).as_posix() for path in OVERLAY.rglob("*") if path.is_file()}
    assert actual == builder.SOURCE_OVERLAY_FILES
    assert "www/dashboard.html" not in actual
    raw = (OVERLAY / "etc/lyoko/frontend.env").read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    builder.validate_source_overlay()


def test_manifest_is_rootfs_only_identity_candidate() -> None:
    data = manifest(F310)
    assert data["schema"] == "openmitrastar.f310-canonical-frontend-identity-candidate/v1"
    assert data["classification"] == "PRIVATE_DEVICE_BOUND_MTD4_CANONICAL_FRONTEND_IDENTITY_FIX_CANDIDATE"
    assert data["candidate_eligible"] is True
    assert data["release_eligible"] is False
    assert data["flash_supported"] is True
    assert data["physical_validation"]["status"] == "NOT_RUN"
    assert data["integration"]["frontend_env_lf_only"] is True
    assert data["integration"]["api_change_limited_to_terminal_cr_normalization"] is True


def test_kernel_config_dtb_and_vmlinux_are_exact_f309() -> None:
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F310 / named("f310", suffix)) == sha256(F309 / named("f309", suffix))


def test_rootfs_diff_is_exact_and_public_dashboard_remains_absent(roots: dict[str, Path]) -> None:
    data = manifest(F310)
    assert set(data["foundation_assets"]["rootfs_diff"]["changed_paths"]) == builder.EXPECTED_ROOTFS_CHANGES
    assert not (roots["f309"] / "www/dashboard.html").exists()
    assert not (roots["f310"] / "www/dashboard.html").exists()
    internal = roots["f310"] / "usr/share/openmitrastar/web/dashboard.html"
    assert internal.is_file()
    assert "6.7.5-f310" in internal.read_text(encoding="utf-8")


def test_frontend_env_is_canonical_and_assets_match(roots: dict[str, Path]) -> None:
    root = roots["f310"]
    raw = (root / "etc/lyoko/frontend.env").read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
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


def test_api_change_is_exactly_two_terminal_cr_trims(roots: dict[str, Path]) -> None:
    old = (roots["f309"] / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    new = (roots["f310"] / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    assert new.count('sub(/\\r$/,"")') == 2
    assert new.replace('sub(/\\r$/,"");', "") == old


def test_busybox_api_emulator_returns_exact_values_without_cr_or_spaces(tmp_path: Path, roots: dict[str, Path]) -> None:
    assert BUSYBOX.is_file()
    frontend = tmp_path / "frontend.env"
    release = tmp_path / "release"
    frontend.write_bytes(
        b"LYOKO_UI_VERSION=6.7.5\r\n"
        b"LYOKO_UI_BUILD_ID=9296308602c7fd90\r\n"
        b"LYOKO_UI_SOURCE=lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device\r\n"
        b"LYOKO_UI_ASSET_BYTES=147589\r\n"
        b"LYOKO_UI_DASHBOARD_HTML_SHA256=6cf88224bd6225e90ac635bba947f326a0e95979ab7e2e9a71494dcb59b8e7f7\r\n"
        b"LYOKO_UI_APP_JS_SHA256=31246030262fc8135da6b5d3742ebc9309ea90bb2858445ffe5e8fdecee2b1a3\r\n"
        b"LYOKO_UI_APP_CSS_SHA256=14629d67bc0fbac483685fe44b36582e73469b71380d554a6fa747b1e9f18172\r\n"
        b"LYOKO_UI_CAPABILITIES_CSS_SHA256=b3f79bff41243ce142a3b2ee957664eddf33833c7f1b0b095d2253ddbededc52\r\n"
        b"LYOKO_UI_LAYOUT_FIXES_CSS_SHA256=ace1f53a940fb4b5fb02d60c6845079bca61995a618b14de6007579fdd6e2408\r\n"
        b"LYOKO_UI_LOGIN_HTML_SHA256=99246625062703c4edb364a443c6b4863807776558dedb726f0f155638ca0aed\r\n"
        b"LYOKO_UI_LOGIN_CSS_SHA256=9cd74ad08f931534ac07c963beb3d1192d69d81d8cfe4e0850ed9a9c5261b31b\r\n"
    )
    release.write_bytes(
        b"OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device\r\n"
        b"OPENMITRASTAR_BUILD_ID=test-build\r\n"
    )
    environment = os.environ.copy()
    environment.update({
        "REQUEST_METHOD": "GET",
        "OM_API_AUTH_BYPASS": "1",
        "OM_FRONTEND_IDENTITY": str(frontend),
        "OM_RELEASE_FILE": str(release),
    })
    proc = subprocess.run(
        [str(BUSYBOX), "ash", str(roots["f310"] / "usr/libexec/openmitrastar/om-api-v1"), "frontend"],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    body = proc.stdout.replace("\r\n", "\n").split("\n\n", 1)[-1].strip()
    payload = json.loads(body)
    assert payload["ui_version"] == "6.7.5"
    assert payload["source"] == "lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device"
    assert payload["firmware_version"] == "lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device"
    assert all("\r" not in str(value) and str(value) == str(value).strip() for value in payload.values())


def test_login_cgi_credentials_and_other_assets_are_exact_f309(roots: dict[str, Path]) -> None:
    for relative in (
        "usr/libexec/openmitrastar/om-oem-cgi", "www/dashboard.cgi", "www/index.cgi",
        "www/login.html", "www/login.css", "www/app.js", "www/app.css",
        "www/capabilities.css", "www/layout-fixes.css", "www/assets/logo.svg",
        "www/assets/movistar-logo.svg", "www/assets/movistar-m.png",
        "www/assets/router-label-help-sanitized.jpg", "www/assets/telefonica-logo.svg",
    ):
        assert sha256(roots["f310"] / relative) == sha256(roots["f309"] / relative)
    old_manifest = manifest(F309)
    new_manifest = manifest(F310)
    assert new_manifest["device_identity"] == old_manifest["device_identity"]
    assert new_manifest["web_identity"] == old_manifest["web_identity"]


def test_all_86_radio_files_are_byte_identical_to_f309(roots: dict[str, Path]) -> None:
    old = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f309"], "podman-mem9-tidb")))
    new = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f310"], "podman-mem9-tidb")))
    assert len(old) == 86
    assert new == old
    data = manifest(F310)
    assert data["integration"]["radio_payload_file_count"] == 86
    assert data["integration"]["radio_payload_byte_identical_to_f309"] is True
    assert data["integration"]["reproducible_two_builds"] is True


def test_candidate_layout_slot_fit_and_sha256sums() -> None:
    data = manifest(F310)
    candidate = F310 / data["artifacts"]["webformat"]["file"]
    rootfs = F310 / named("f310", ".rootfs.squashfs")
    payload = candidate.read_bytes()
    assert candidate.stat().st_size == data["artifacts"]["webformat"]["bytes"]
    assert sha256(candidate) == data["artifacts"]["webformat"]["sha256"]
    assert payload[builder.f306.ROOTFS_OFFSET:] == rootfs.read_bytes()
    assert payload[builder.f306.ROOTFS_OFFSET:builder.f306.ROOTFS_OFFSET + 4] == b"hsqs"
    assert len(payload) <= builder.f306.STORE_SLOT_OFFSET
    assert data["storage"]["store_erased_ff"] is True

    sums = {}
    for line in (F310 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    actual = {path.name: sha256(path) for path in F310.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    assert sums == actual
