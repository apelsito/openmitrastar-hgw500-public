from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f191_network_security_integration as f191  # noqa: E402


def test_built_integration_contract() -> None:
    manifest_path = f191.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f189 = json.loads((f191.F189_BUILD / "manifest.json").read_text(encoding="ascii"))
    f190 = json.loads((f191.F190_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f191-network-security-integration/v1"
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == f189["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["parents"]["f190_rootfs_sha256"] == f190["artifacts"]["rootfs_squashfs"]["sha256"]
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.0.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.0-f191"
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/sbin/om-multicast-policy" in changed
    assert "etc/init.d/S33-multicast-policy" in changed
    assert "usr/share/openmitrastar/keys/device-dropbear-ed25519-host-key" not in manifest["foundation_assets"]["rootfs_diff"]["new"]
    config = (f191.OUT / f"{f191.BASE}.config").read_text(encoding="utf-8")
    assert "CONFIG_IP_MULTICAST=y\n" in config
    assert "CONFIG_BRIDGE_IGMP_SNOOPING=y\n" in config
    assert "CONFIG_VLAN_8021Q=y\n" in config


def test_builder_is_offline_only() -> None:
    source = Path(f191.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
