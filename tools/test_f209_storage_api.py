from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f209_storage_api as f209  # noqa: E402


def test_frozen_storage_api_contract() -> None:
    overlay = f209.OVERLAY
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    html = (overlay / "www/dashboard.html").read_text(encoding="utf-8")
    assert "storage)" in api
    assert '"writes_enabled":false' in api
    assert '"mtd5_policy":"protected-not-package-storage"' in api
    assert 'id="storage"' in html and 'id="storage-raw"' in html


def test_built_f209_contract() -> None:
    manifest_path = f209.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f209.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f209-storage-api/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["frontend"]["ui_version"] == "2.9.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.9-f209"
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["storage"]["store_erased_ff"] is True
    assert manifest["storage"]["candidate_ends_before_store"] is True
    assert manifest["spi_probe"]["write"] is False
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert "www/api/v1/storage" in changed
    assert "www/dashboard.html" in changed
    assert "www/app.js" in changed
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"
    assert manifest["runtime_signature_verifier"]["sha256"] == "831ea6de598834222c6e6e597b13f297aeaf5d472a55de0a7535419e978442b7"


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f209.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
