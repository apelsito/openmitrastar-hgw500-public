from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-3.9-f225"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F224 = PRIVATE / "f224-device-bound"
F225 = PRIVATE / "f225-device-bound"
F224_BASE = "openmitrastar-linux510-f224-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
F225_BASE = "openmitrastar-linux510-f225-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_has_structured_review_and_faithful_emulator_guards() -> None:
    app = (FOUNDATION / "overlay/www/app.js").read_text(encoding="utf-8")
    html = (FOUNDATION / "overlay/www/dashboard.html").read_text(encoding="utf-8")
    py = (FOUNDATION / "emulator/server.py").read_text(encoding="utf-8")
    mjs = (FOUNDATION / "emulator/server.mjs").read_text(encoding="utf-8")
    transaction = (FOUNDATION / "overlay/usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    for marker in ("renderTransaction", "transactionFieldRows", "transaction-error", "error.detail", "error.transactionId"):
        assert marker in app or marker in html
    for source in (py, mjs):
        for marker in ("invalid-channel", "transaction-conflict", "confirmation-required", "rollback-verify-failed", "recovery-required"):
            assert marker in source
    assert '"snapshot":{"before":' in transaction
    assert "config_json \"$rollback\"" in transaction


def test_built_f225_preserves_f224_kernel_and_contract() -> None:
    manifest_path = F225 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f225-transaction-review/v1"
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert all(manifest["transaction_review"].values())
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F225 / f"{F225_BASE}{suffix}") == sha256(F224 / f"{F224_BASE}{suffix}")
