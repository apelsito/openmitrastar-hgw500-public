from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f199_transaction_v2 as f199  # noqa: E402


def test_frozen_transaction_v2_contract() -> None:
    overlay = f199.OVERLAY
    transaction = (overlay / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    frontend = (overlay / "www/app.js").read_text(encoding="utf-8")
    for marker in (
        "pending-v2.conf", "applied-v2.conf", "transaction-v2.lock", "OM_CONFIG_OWNER",
        "OM_CONFIG_TXN_ID", "expires_at", "transaction-conflict", "transaction-owner-mismatch",
        "transaction-applied", "rollback-verify-failed",
    ):
        assert marker in transaction
    assert "HTTP_X_OM_TRANSACTION" in api
    assert "transaction_owner" in api
    assert "X-OM-Transaction" in frontend
    assert (overlay / "www/api/v1/config/status").is_file()


def test_built_f199_contract() -> None:
    manifest_path = f199.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f199.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f199-transaction-v2/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.5.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.5-f199"
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/sbin/om-config-transaction" in changed
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert "www/api/v1/config/status" in changed
    assert "www/app.js" in changed
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f199.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
