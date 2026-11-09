from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F223 = PRIVATE / "f223-device-bound"
F225 = PRIVATE / "f225-device-bound"
F226 = PRIVATE / "f226-device-bound"
DEVICE = "hgw500bna-qcv2-a2-primary"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f226_exactly_integrates_f223_kernel_and_f225_rootfs() -> None:
    manifest_path = F226 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f226-integrated-rxring-foundation/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F226 / named("f226", suffix)) == sha256(F223 / named("f223", suffix))
    assert sha256(F226 / named("f226", ".rootfs.squashfs")) == sha256(F225 / named("f225", ".rootfs.squashfs"))
    assert manifest["integration"]["additional_changes"] == []
    assert len(manifest["promotion_blockers"]) == 2
