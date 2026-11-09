from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import build_f313_full_developer_qtn_controls_from_f312 as builder


DEVICE = "hgw500bna-qcv2-a2-primary"
PRIVATE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F312 = PRIVATE / "f312-device-bound"
F313 = PRIVATE / "f313-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="ascii"))


@pytest.fixture(scope="session")
def roots() -> dict[str, Path]:
    root = builder.ROOT / ".codex_tmp/test-f313-full-rootfs"
    if root.exists():
        shutil.rmtree(root.resolve())
    old = root / "f312"
    new = root / "f313"
    root.mkdir(parents=True)
    builder.f306.extract_rootfs(F312 / named("f312", ".rootfs.squashfs"), old, "podman-mem9-tidb")
    builder.f306.extract_rootfs(F313 / named("f313", ".rootfs.squashfs"), new, "podman-mem9-tidb")
    yield {"f312": old, "f313": new}
    if root.exists():
        shutil.rmtree(root.resolve())


def test_manifest_and_kernel_contract() -> None:
    data = manifest(F313)
    assert data["schema"] == "openmitrastar.f313-full-developer-qtn-controls-candidate/v1"
    assert data["classification"] == "PRIVATE_DEVICE_BOUND_MTD4_FULL_DEVELOPER_QTN_CONTROLS_CANDIDATE"
    assert data["candidate_eligible"] is True
    assert data["flash_supported"] is True
    assert data["physical_validation"]["status"] == "NOT_RUN"
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F313 / named("f313", suffix)) == sha256(F312 / named("f312", suffix))


def test_exact_rootfs_scope_and_radio_binary_preservation(roots: dict[str, Path]) -> None:
    data = manifest(F313)
    assert set(data["foundation_assets"]["rootfs_diff"]["changed_paths"]) == builder.EXPECTED_ROOTFS_CHANGES
    old = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f312"], "podman-mem9-tidb")))
    new = builder.f306.radio_hashes(builder.f306.file_hashes(builder.f306.tree_inventory(roots["f313"], "podman-mem9-tidb")))
    changed = {name for name in set(old) | set(new) if old.get(name) != new.get(name)}
    assert changed == {"usr/sbin/om-qtnctl", "usr/sbin/om-radioctl"}
    for name in old:
        if name.endswith(".ko") or name.startswith("lib/firmware/"):
            assert old[name] == new[name]


def test_developer_ui_has_real_advanced_controls(roots: dict[str, Path]) -> None:
    root = roots["f313"]
    dashboard = (root / "usr/share/openmitrastar/web/dashboard.html").read_text(encoding="utf-8")
    assert "Profundidad de administración" not in dashboard
    for name in (
        "ssid_broadcast", "client_isolation", "wmm", "short_gi",
        "beacon_interval", "dtim_period", "retry_count", "ldpc",
        "forty_only", "ba_control", "ba_max", "ampdu_density",
        "tpc_interval", "multicast_rate",
    ):
        assert f'name="{name}"' in dashboard
    assert 'name="channel"' in dashboard and 'name="bandwidth"' in dashboard
    assert "Hardware DFS presente" in dashboard


def test_backend_bounds_rollback_and_dfs_hold(roots: dict[str, Path]) -> None:
    root = roots["f313"]
    qtnctl = (root / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    transaction = (root / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    radioctl = (root / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    assert "rollback_dynamic_order=" in qtnctl
    assert 'dtim_period) integer_range "$2" 1 15' in qtnctl
    assert 'multicast_rate) integer_range "$2" 256 54000' in qtnctl
    assert "dfs-fail-closed-channel-bandwidth-hold" in qtnctl
    assert '5g:channel|5g:bandwidth) return 1' in transaction
    assert '"schema":"lyoko.radio.settings/v2"' in radioctl
    assert '"physical_certification":"pending"' in radioctl


def test_frontend_identity_and_hashes(roots: dict[str, Path]) -> None:
    root = roots["f313"]
    values = dict(line.split("=", 1) for line in (root / "etc/lyoko/frontend.env").read_text(encoding="ascii").splitlines() if "=" in line)
    assert values["LYOKO_UI_VERSION"] == "6.8.1"
    assert values["LYOKO_UI_SOURCE"] == builder.PRODUCT_VERSION
    total = 0
    for key, relative in builder.FRONTEND_ASSETS.items():
        assert values[key] == sha256(root / relative)
        total += (root / relative).stat().st_size
    assert int(values["LYOKO_UI_ASSET_BYTES"]) == total


def test_candidate_layout_and_sha256sums() -> None:
    data = manifest(F313)
    candidate = F313 / data["artifacts"]["webformat"]["file"]
    rootfs = F313 / named("f313", ".rootfs.squashfs")
    payload = candidate.read_bytes()
    assert sha256(candidate) == data["artifacts"]["webformat"]["sha256"]
    assert payload[builder.f306.ROOTFS_OFFSET:] == rootfs.read_bytes()
    assert len(payload) <= builder.f306.STORE_SLOT_OFFSET
    sums = {
        name: digest
        for digest, name in (
            line.split("  ", 1)
            for line in (F313 / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        )
    }
    actual = {path.name: sha256(path) for path in F313.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    assert sums == actual
