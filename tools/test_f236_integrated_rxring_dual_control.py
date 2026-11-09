from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F223 = PRIVATE / "f223-device-bound"
F235 = PRIVATE / "f235-device-bound"
F236 = PRIVATE / "f236-device-bound"
DEVICE = "hgw500bna-qcv2-a2-primary"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f236_is_exact_f223_kernel_plus_f235_rootfs_hold() -> None:
    manifest_path = F236 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f236-integrated-rxring-dual-control/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["integration"]["additional_changes"] == []
    assert manifest["integration"]["native_qtn_control"]["backend"] == "wext-hostapd-restart"
    assert manifest["integration"]["native_rtl_control"]["backend"] == "nl80211-hostapd-reload"
    assert manifest["integration"]["config_apply"]["enabled"] is True
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F236 / named("f236", suffix)) == sha256(F223 / named("f223", suffix))
    assert sha256(F236 / named("f236", ".rootfs.squashfs")) == sha256(F235 / named("f235", ".rootfs.squashfs"))
