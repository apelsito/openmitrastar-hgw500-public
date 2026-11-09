from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import build_f304_api_contract_from_f301 as builder


DEVICE = "hgw500bna-qcv2-a2-primary"
FIRMWARE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F301 = FIRMWARE / "f301-device-bound"
F304 = FIRMWARE / "f304-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="session")
def extracted() -> dict[str, Path]:
    root = builder.ROOT / ".codex_tmp/test-f304-api-rootfs"
    before = root / "f301"
    after = root / "f304"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    builder.extract_rootfs(F301 / named("f301", ".rootfs.squashfs"), before, "podman-mem9-tidb")
    builder.extract_rootfs(F304 / named("f304", ".rootfs.squashfs"), after, "podman-mem9-tidb")
    yield {"f301": before, "f304": after}
    shutil.rmtree(root, ignore_errors=True)


def test_source_overlay_is_api_only() -> None:
    actual = {
        path.relative_to(builder.FOUNDATION_SOURCE).as_posix()
        for path in builder.FOUNDATION_SOURCE.rglob("*")
        if path.is_file()
    }
    assert actual == {"usr/libexec/openmitrastar/om-api-v1"}


def test_manifest_is_offline_and_fail_closed() -> None:
    manifest = json.loads((F304 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f304-api-contract-offline/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["api_contract"] == {
        "base": "F301",
        "canonical_radio_patch": True,
        "dfs_write_enabled": False,
        "firmware_write_api": False,
        "hardware_status": "NOT_RUN",
        "legacy_stage_alias": True,
        "package_install_scope": "ram-only and feature-gated",
        "persistent_config_writes": False,
        "persistent_package_writes": False,
        "rootfs_size_source": "/proc/mtd",
        "schema": "lyoko.api.audit/v1",
    }
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == builder.EXPECTED_ROOTFS_CHANGES


def test_kernel_radio_frontend_and_identity_are_unchanged(extracted: dict[str, Path]) -> None:
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F304 / named("f304", suffix)) == sha256(F301 / named("f301", suffix))

    before = builder.tree_inventory(extracted["f301"], "podman-mem9-tidb")
    after = builder.tree_inventory(extracted["f304"], "podman-mem9-tidb")
    before_hashes = builder.file_hashes(before)
    after_hashes = builder.file_hashes(after)
    assert builder.radio_hashes(before_hashes) == builder.radio_hashes(after_hashes)
    for path in builder.FRONTEND_ASSETS.values():
        assert before_hashes[path] == after_hashes[path]
    identity_path = "usr/share/openmitrastar/device-identity/dropbear_ed25519_host_key"
    assert before_hashes[identity_path] == after_hashes[identity_path]


def test_packaged_api_contains_only_safe_contract_changes(extracted: dict[str, Path]) -> None:
    source = (extracted["f304"] / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    assert 'PATCH) stage_radio_config "$band"' in source
    assert 'radios/2g/stage|radios/5g/stage)' in source
    assert 'rootfs_bytes=$(mtd_named_bytes rootfs_live)' in source
    assert '"firmware_write_api":false' in source
    assert '"persistent_config_writes":false' in source
    assert '"persistent_package_writes":false' in source
    assert 'runtime_install_scope":"ram-only"' in source
    assert "dfs-radar-backend-unavailable" in source
    for forbidden in ("flash_erase", "mtd_debug", "nandwrite", "fw_setenv", "mount -o remount,rw"):
        assert forbidden not in source


def test_artifact_hashes_and_store_boundary() -> None:
    manifest = json.loads((F304 / "manifest.json").read_text(encoding="ascii"))
    candidate = F304 / manifest["artifacts"]["webformat"]["file"]
    rootfs = F304 / manifest["artifacts"]["rootfs_squashfs"]["file"]
    data = candidate.read_bytes()
    assert sha256(candidate) == manifest["artifacts"]["webformat"]["sha256"]
    assert sha256(rootfs) == manifest["artifacts"]["rootfs_squashfs"]["sha256"]
    assert data[builder.ROOTFS_OFFSET:] == rootfs.read_bytes()
    assert len(data) <= builder.STORE_SLOT_OFFSET
    assert all(value == 0xFF for value in (data + b"\xff" * (builder.SLOT_SIZE - len(data)))[builder.STORE_SLOT_OFFSET:])


def test_builder_has_no_hardware_transport() -> None:
    source = Path(builder.__file__).read_text(encoding="utf-8")
    for forbidden in ("COM3", "plink", "ssh.exe", "tftp.exe", "flash_erase", "mtd_debug", "reboot"):
        assert forbidden not in source
    assert '"hardware_actions": {"router": False, "uart": False, "ssh": False, "tftp": False, "flash": False}' in source
