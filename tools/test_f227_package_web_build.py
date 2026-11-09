from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F225 = PRIVATE / "f225-device-bound"
F227 = PRIVATE / "f227-device-bound"


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f227_build_preserves_kernel_and_store_policy() -> None:
    manifest_path = F227 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    parent = json.loads((F225 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f227-package-web/v1"
    assert manifest["package_web"]["feature_gate_default"] == "disabled"
    assert manifest["package_web"]["persistent_install"] is False
    assert manifest["package_web"]["network_fetch"] is False
    assert manifest["package_web"]["exec_over_http"] is False
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F227 / artifact("f227", suffix)) == sha256(F225 / artifact("f225", suffix))
    assert manifest["layout"]["mtd_mapping"] == parent["layout"]["mtd_mapping"]
    assert manifest["storage"] == parent["storage"]
