from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F223 = PRIVATE / "f223-device-bound"
F231 = PRIVATE / "f231-device-bound"
F232 = PRIVATE / "f232-device-bound"
DEVICE = "hgw500bna-qcv2-a2-primary"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f232_is_exact_f223_kernel_plus_f231_rootfs_hold() -> None:
    manifest_path = F232 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f232-integrated-rxring-radio-truth/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["integration"]["additional_changes"] == []
    assert manifest["integration"]["radio_control_backend"]["missing_behavior"].endswith("fail-closed")
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F232 / named("f232", suffix)) == sha256(F223 / named("f223", suffix))
    assert sha256(F232 / named("f232", ".rootfs.squashfs")) == sha256(F231 / named("f231", ".rootfs.squashfs"))
