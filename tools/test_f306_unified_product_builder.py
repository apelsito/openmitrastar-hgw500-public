from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import build_f306_unified_product_from_f305 as builder


DEVICE = "hgw500bna-qcv2-a2-primary"
PRIVATE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F301 = PRIVATE / "f301-device-bound"
F305 = PRIVATE / "f305-device-bound"
F306 = PRIVATE / "f306-device-bound"
SOURCE = builder.FOUNDATION_ROOT
OVERLAY = builder.FOUNDATION_SOURCE


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict:
    return json.loads((path / "manifest.json").read_text(encoding="ascii"))


def parse_env(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="ascii").splitlines() if "=" in line)


@pytest.fixture(scope="session")
def extracted() -> dict[str, Path]:
    root = builder.ROOT / ".codex_tmp/test-f306-unified-rootfs"
    if root.exists():
        resolved = root.resolve()
        expected = (builder.ROOT / ".codex_tmp/test-f306-unified-rootfs").resolve()
        assert resolved == expected and builder.ROOT.resolve() in resolved.parents
        shutil.rmtree(resolved)
    f301 = root / "f301"
    f306 = root / "f306"
    root.mkdir(parents=True)
    builder.extract_rootfs(F301 / named("f301", ".rootfs.squashfs"), f301, "podman-mem9-tidb")
    builder.extract_rootfs(F306 / named("f306", ".rootfs.squashfs"), f306, "podman-mem9-tidb")
    yield {"f301": f301, "f306": f306}
    if root.exists():
        shutil.rmtree(root.resolve())


def test_source_overlay_is_exact_and_coherent() -> None:
    actual = {path.relative_to(OVERLAY).as_posix() for path in OVERLAY.rglob("*") if path.is_file()}
    assert actual == builder.SOURCE_OVERLAY_FILES
    assert SOURCE.name == "lyoko-foundation-6.7.3-f306-unified-product"
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in OVERLAY.rglob("*")
        if path.is_file() and b"\0" not in path.read_bytes()
    )
    for stale in ("F301", "F304", "F305", "f301", "f304", "f305", "6.7.0", "6.7.1", "6.7.2"):
        assert stale not in combined


def test_source_preserves_the_f305_console_and_api() -> None:
    assert sha256(OVERLAY / "usr/libexec/openmitrastar/om-api-v1") == sha256(
        builder.F305_SOURCE / "usr/libexec/openmitrastar/om-api-v1"
    )
    for relative in (
        "www/app.css", "www/app.js", "www/capabilities.css", "www/layout-fixes.css",
        "www/login.css", "www/login.html", "www/assets/logo.svg",
        "www/assets/movistar-logo.svg", "www/assets/movistar-m.png",
        "www/assets/router-label-help-sanitized.jpg", "www/assets/telefonica-logo.svg",
    ):
        assert sha256(OVERLAY / relative) == sha256(builder.F305_SOURCE / relative)


def test_manifest_is_flashable_candidate_and_version_coherent() -> None:
    manifest = load_manifest(F306)
    assert manifest["schema"] == "openmitrastar.f306-unified-product-candidate/v1"
    assert manifest["classification"] == "PRIVATE_DEVICE_BOUND_MTD4_PHYSICAL_PROMOTION_CANDIDATE"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["flash_supported"] is True
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["developer_console"]["firmware_line"] == "F306 unified product physical candidate"
    assert manifest["developer_console"]["ui_version"] == "6.7.3"
    assert manifest["developer_console"]["ui_modes"] == ["Normal", "Advanced", "Developer"]


def test_kernel_config_dtb_and_vmlinux_are_byte_identical_to_f301() -> None:
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F306 / named("f306", suffix)) == sha256(F301 / named("f301", suffix))


def test_rootfs_diff_is_exact(extracted: dict[str, Path]) -> None:
    manifest = load_manifest(F306)
    diff = manifest["foundation_assets"]["rootfs_diff"]
    assert set(diff["changed_paths"]) == builder.EXPECTED_ROOTFS_CHANGES
    packed_modes = builder.squashfs_modes(F306 / named("f306", ".rootfs.squashfs"), "podman-mem9-tidb")
    for name, expected in builder.EXPECTED_MODES.items():
        assert packed_modes[name] == expected


def test_86_radio_files_are_byte_identical_to_f301(extracted: dict[str, Path]) -> None:
    old = builder.radio_hashes(builder.file_hashes(builder.tree_inventory(extracted["f301"], "podman-mem9-tidb")))
    new = builder.radio_hashes(builder.file_hashes(builder.tree_inventory(extracted["f306"], "podman-mem9-tidb")))
    assert len(old) == 86
    assert new == old
    manifest = load_manifest(F306)
    assert manifest["integration"]["radio_payload_file_count"] == 86
    assert manifest["integration"]["radio_payload_byte_identical_to_f301"] is True


def test_runtime_identity_and_complete_asset_hashes(extracted: dict[str, Path]) -> None:
    root = extracted["f306"]
    release = parse_env(root / "etc/openmitrastar/release")
    frontend = parse_env(root / "etc/lyoko/frontend.env")
    assert release["OPENMITRASTAR_PRODUCT_VERSION"] == "lyoko-foundation-6.7.3-f306-unified-product-device"
    assert release["OPENMITRASTAR_UI_VERSION"] == "6.7.3"
    assert frontend["LYOKO_UI_VERSION"] == "6.7.3"
    assert frontend["LYOKO_UI_SOURCE"] == "lyoko-foundation-6.7.3-f306-unified-product"
    total = 0
    for key, relative in builder.FRONTEND_ASSETS.items():
        asset = root / relative
        assert frontend[key] == sha256(asset)
        total += asset.stat().st_size
    assert int(frontend["LYOKO_UI_ASSET_BYTES"]) == total
    builder.validate_runtime_text(root, "podman-mem9-tidb")


def test_three_modes_login_and_dashboard_are_packaged(extracted: dict[str, Path]) -> None:
    root = extracted["f306"]
    dashboard = (root / "usr/share/openmitrastar/web/dashboard.html").read_text(encoding="utf-8")
    assert dashboard == (root / "www/dashboard.html").read_text(encoding="utf-8")
    assert 'content="6.7.3"' in dashboard
    for mode in ("normal", "advanced", "developer"):
        assert f'data-mode="{mode}"' in dashboard
    assert "6.7.3-f306" in dashboard
    assert "Mira debajo del router" in (root / "www/login.html").read_text(encoding="utf-8")
    cgi = (root / "usr/libexec/openmitrastar/om-oem-cgi").read_text(encoding="utf-8")
    assert "redirect /dashboard.cgi" in cgi
    assert "dashboard.cgi) title='Lyoko'; view='dashboard'" in cgi


def test_api_contract_and_capabilities_are_current(extracted: dict[str, Path]) -> None:
    root = extracted["f306"]
    api = (root / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    for marker in (
        "stage_radio_config", "radios/2g|radios/5g", "radios/2g/stage|radios/5g/stage",
        "PATCH) stage_radio_config", "mtd_named_bytes",
        "firmware_write_api", "persistent_package_writes",
    ):
        assert marker in api
    capabilities = json.loads((root / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    assert capabilities["source"] == "lyoko-f306-unified-product-f300-evidence-registry"
    assert len(capabilities["items"]) == 23


def test_f305_functional_assets_are_preserved_except_identity_files(extracted: dict[str, Path]) -> None:
    f305_root = builder.ROOT / ".codex_tmp/test-f306-f305-rootfs"
    if f305_root.exists():
        shutil.rmtree(f305_root)
    try:
        builder.extract_rootfs(F305 / named("f305", ".rootfs.squashfs"), f305_root, "podman-mem9-tidb")
        f306_root = extracted["f306"]
        for relative in (
            "usr/libexec/openmitrastar/om-api-v1",
            "www/app.js", "www/app.css", "www/capabilities.css", "www/layout-fixes.css",
            "www/login.html", "www/login.css", "www/assets/logo.svg",
            "www/assets/movistar-logo.svg", "www/assets/movistar-m.png",
            "www/assets/router-label-help-sanitized.jpg", "www/assets/telefonica-logo.svg",
        ):
            assert sha256(f306_root / relative) == sha256(f305_root / relative)
    finally:
        if f305_root.exists():
            shutil.rmtree(f305_root)


def test_store_observer_disabled_and_multicast_inactive(extracted: dict[str, Path]) -> None:
    root = extracted["f306"]
    store = (root / "etc/openmitrastar/features/store-protection-observer-v1").read_text(encoding="ascii")
    assert "OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0" in store
    assert "OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0" in store
    assert "OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0" in store
    assert "OPENMITRASTAR_MULTICAST_CERT=1" in (root / "etc/openmitrastar/features/multicast-cert-v1").read_text(encoding="ascii")
    init_text = "\n".join(path.read_text(encoding="utf-8") for path in (root / "etc/init.d").iterdir() if path.is_file())
    assert "qtn-topaz-store-protection-observer" not in init_text
    assert "om-multicast-cert" not in init_text


def test_candidate_layout_hashes_and_store_boundary() -> None:
    manifest = load_manifest(F306)
    candidate = F306 / manifest["artifacts"]["webformat"]["file"]
    rootfs = F306 / named("f306", ".rootfs.squashfs")
    data = candidate.read_bytes()
    assert candidate.stat().st_size == manifest["artifacts"]["webformat"]["bytes"]
    assert sha256(candidate) == manifest["artifacts"]["webformat"]["sha256"]
    assert data[builder.ROOTFS_OFFSET:] == rootfs.read_bytes()
    assert data[builder.ROOTFS_OFFSET:builder.ROOTFS_OFFSET + 4] == b"hsqs"
    assert len(data) <= builder.STORE_SLOT_OFFSET
    assert manifest["storage"]["store_erased_ff"] is True


def test_sha256sums_cover_every_packaged_artifact() -> None:
    sums = {}
    for line in (F306 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    actual = {path.name: sha256(path) for path in F306.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    assert sums == actual

