from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F223 = PRIVATE / "f223-device-bound"
F227 = PRIVATE / "f227-device-bound"
F228 = PRIVATE / "f228-device-bound"
DEVICE = "hgw500bna-qcv2-a2-primary"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f228_exactly_integrates_f223_kernel_and_f227_rootfs() -> None:
    manifest_path = F228 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f228-integrated-rxring-package-web/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        assert sha256(F228 / named("f228", suffix)) == sha256(F223 / named("f223", suffix))
    assert sha256(F228 / named("f228", ".rootfs.squashfs")) == sha256(F227 / named("f227", ".rootfs.squashfs"))
    assert manifest["integration"]["additional_changes"] == []
    assert len(manifest["promotion_blockers"]) == 2
