from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f183_capability_registry as f183  # noqa: E402


def test_registry_contract() -> None:
    registry = json.loads((f183.OVERLAY / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    states = {item["state"] for item in registry["items"]}
    assert states == {"available", "readonly", "experimental", "blocked", "unsupported", "certification_required"}
    assert len(registry["items"]) == 16
    assert all(set(item) == {"id", "domain", "state", "mode", "risk", "evidence", "backend"} for item in registry["items"])


def test_built_contract() -> None:
    manifest_path = f183.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f183.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f183-capability-registry/v1"
    assert manifest["capability_registry"]["items"] == 16
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["package_manager"] == source["package_manager"]
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    for required in (
        "etc/lyoko/capabilities.json",
        "usr/libexec/openmitrastar/om-api-v1",
        "www/api/v1/capabilities",
        "www/app.js",
        "www/capabilities.css",
        "www/dashboard.html",
    ):
        assert required in changed
