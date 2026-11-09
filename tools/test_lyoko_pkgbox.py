from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/packages/lyoko-pkgbox"


def test_pkgbox_manifest_contract() -> None:
    manifest_path = OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "lyoko.pkgbox/v1"
    assert manifest["architecture"] == "arc700_uclibc_lyoko_v1"
    assert manifest["network_fetch"] is False
    assert manifest["flash_tools"] is False
    assert manifest["dynamic_install_enabled"] is False
    assert {"ar", "tar", "gzip", "gunzip", "sha256sum"}.issubset(manifest["required_applets"])


def test_pkgbox_has_no_private_key_material() -> None:
    if not OUT.is_dir():
        return
    names = {path.name.lower() for path in OUT.iterdir() if path.is_file()}
    assert not any(name.endswith((".key", ".pem")) for name in names)
