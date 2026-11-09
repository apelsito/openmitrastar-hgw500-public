from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f185_web_provenance as f185  # noqa: E402


def test_frozen_frontend_identity() -> None:
    identity = f185.frontend_identity()
    assert identity["LYOKO_UI_VERSION"] == "1.5.0"
    assert identity["LYOKO_UI_SOURCE"] == "lyoko-foundation-1.5-f185"
    assert len(identity["LYOKO_UI_BUILD_ID"]) == 16
    assert int(identity["LYOKO_UI_ASSET_BYTES"]) < 64 * 1024


def test_built_f185_contract() -> None:
    manifest_path = f185.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f185.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f185-web-provenance/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["source"] == "lyoko-foundation-1.5-f185"
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    for required in (
        "etc/lyoko/frontend.env",
        "usr/libexec/openmitrastar/om-api-v1",
        "www/api/v1/frontend",
        "www/app.css",
        "www/app.js",
        "www/dashboard.html",
    ):
        assert required in changed


def test_f185_has_no_flash_or_storage_logic() -> None:
    source = Path(f185.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "lyoko_store"):
        assert forbidden not in source
