from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import build_f311_qtn_capability_truth_from_f310 as builder


DEVICE = "hgw500bna-qcv2-a2-primary"
PRIVATE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F310 = PRIVATE / "f310-device-bound"
F311 = PRIVATE / "f311-device-bound"
OVERLAY = builder.FOUNDATION_SOURCE


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="ascii"))


@pytest.fixture(scope="session")
def roots() -> dict[str, Path]:
    root = builder.ROOT / ".codex_tmp/test-f311-qtn-capability-truth-rootfs"
    if root.exists():
        shutil.rmtree(root.resolve())
    old = root / "f310"
    new = root / "f311"
    root.mkdir(parents=True)
    builder.f306.extract_rootfs(F310 / named("f310", ".rootfs.squashfs"), old, "podman-mem9-tidb")
    builder.f306.extract_rootfs(F311 / named("f311", ".rootfs.squashfs"), new, "podman-mem9-tidb")
    yield {"f310": old, "f311": new}
    if root.exists():
        shutil.rmtree(root.resolve())


def test_source_contract_is_explicit() -> None:
    actual = {path.relative_to(OVERLAY).as_posix() for path in OVERLAY.rglob("*") if path.is_file()}
    assert actual == builder.SOURCE_OVERLAY_FILES
    assert "www/dashboard.html" not in actual
    builder.validate_source_overlay()


def test_manifest_is_guarded_rootfs_candidate() -> None:
    data = manifest(F311)
    assert data["schema"] == "openmitrastar.f311-qtn-capability-truth-candidate/v1"
    assert data["classification"] == "PRIVATE_DEVICE_BOUND_MTD4_QTN_CAPABILITY_TRUTH_CANDIDATE"
    assert data["candidate_eligible"] is True
    assert data["release_eligible"] is False
    assert data["flash_supported"] is True
    assert data["physical_validation"]["status"] == "NOT_RUN"


def test_kernel_and_binary_radio_payload_are_exact_f310(roots: dict[str, Path]) -> None:
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F311 / named("f311", suffix)) == sha256(F310 / named("f310", suffix))
    old = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f310"], "podman-mem9-tidb")))
    new = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f311"], "podman-mem9-tidb")))
    changed = {name for name in set(old) | set(new) if old.get(name) != new.get(name)}
    assert changed == {
        "etc/openmitrastar/features/qtn-native-control-v1",
        "usr/sbin/om-qtnctl",
        "usr/sbin/om-radioctl",
    }
    assert len(old) == len(new) == 86


def test_rootfs_diff_and_control_scope(roots: dict[str, Path]) -> None:
    data = manifest(F311)
    assert set(data["foundation_assets"]["rootfs_diff"]["changed_paths"]) == builder.EXPECTED_ROOTFS_CHANGES
    root = roots["f311"]
    assert not (root / "www/dashboard.html").exists()
    assert (root / "etc/openmitrastar/features/qtn-native-control-v1").read_text(encoding="ascii").strip() == "OPENMITRASTAR_QTN_NATIVE_CONTROL=1"
    transaction = (root / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    assert '5g:ssid) safe_ssid "$vp_value"' in transaction
    assert '5g:channel|5g:bandwidth) return 1' in transaction
    qtnctl = (root / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    assert 'qtn-channel-material-change-not-certified' in qtnctl
    assert 'qtn-bandwidth-material-change-not-certified' in qtnctl
    radioctl = (root / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    assert '"scope":"ssid-only"' in radioctl
    assert '"dfs_hardware_present":true' in radioctl
    assert '"writable_settings":["ssid"]' in radioctl


def test_frontend_truth_and_hashes(roots: dict[str, Path]) -> None:
    root = roots["f311"]
    env = dict(line.split("=", 1) for line in (root / "etc/lyoko/frontend.env").read_text(encoding="ascii").splitlines() if "=" in line)
    assert env["LYOKO_UI_VERSION"] == "6.7.6"
    assert env["LYOKO_UI_SOURCE"] == builder.PRODUCT_VERSION
    total = 0
    for key, relative in builder.FRONTEND_ASSETS.items():
        assert env[key] == sha256(root / relative)
        total += (root / relative).stat().st_size
    assert int(env["LYOKO_UI_ASSET_BYTES"]) == total
    app = (root / "www/app.js").read_text(encoding="utf-8")
    dashboard = (root / "usr/share/openmitrastar/web/dashboard.html").read_text(encoding="utf-8")
    assert "Hardware DFS · port pendiente" in app
    assert "Hardware DFS presente · port pendiente" in dashboard


def test_candidate_layout_and_hashes() -> None:
    data = manifest(F311)
    candidate = F311 / data["artifacts"]["webformat"]["file"]
    rootfs = F311 / named("f311", ".rootfs.squashfs")
    payload = candidate.read_bytes()
    assert sha256(candidate) == data["artifacts"]["webformat"]["sha256"]
    assert payload[builder.f306.ROOTFS_OFFSET:] == rootfs.read_bytes()
    assert len(payload) <= builder.f306.STORE_SLOT_OFFSET
    sums = {
        name: digest
        for digest, name in (
            line.split("  ", 1)
            for line in (F311 / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        )
    }
    actual = {path.name: sha256(path) for path in F311.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    assert sums == actual
