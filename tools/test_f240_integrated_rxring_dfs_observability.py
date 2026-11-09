from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F223 = PRIVATE / "f223-device-bound"
F239 = PRIVATE / "f239-device-bound"
F240 = PRIVATE / "f240-device-bound"
DEVICE = "hgw500bna-qcv2-a2-primary"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f240_is_exact_f223_kernel_plus_f239_rootfs_hold() -> None:
    manifest_path = F240 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f240-integrated-rxring-dfs-observability/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["integration"]["additional_changes"] == []
    assert manifest["integration"]["native_qtn_control"]["backend"] == "wext-hostapd-restart"
    assert manifest["integration"]["native_rtl_control"]["backend"] == "nl80211-hostapd-reload"
    assert manifest["integration"]["config_apply"]["enabled"] is True
    assert manifest["integration"]["transaction_hardening"]["expired_applied_transaction"].startswith("automatic verified rollback")
    assert manifest["integration"]["dfs_observability"]["write_operations"] is False
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F240 / named("f240", suffix)) == sha256(F223 / named("f223", suffix))
    assert sha256(F240 / named("f240", ".rootfs.squashfs")) == sha256(F239 / named("f239", ".rootfs.squashfs"))
