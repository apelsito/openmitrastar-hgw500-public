from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F227 = PRIVATE / "f227-device-bound"
F229 = PRIVATE / "f229-device-bound"


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f229_preserves_f227_kernel_and_exposes_read_only_inventory() -> None:
    manifest_path = F229 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f229-hardware-inventory/v1"
    assert manifest["hardware_inventory"]["write_operations"] is False
    assert manifest["hardware_inventory"]["known_polarity"] == {"wifi2g": "active-low"}
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F229 / artifact("f229", suffix)) == sha256(F227 / artifact("f227", suffix))
