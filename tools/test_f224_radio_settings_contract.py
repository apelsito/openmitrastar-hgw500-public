from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-3.8-f224"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F222 = PRIVATE / "f222-device-bound"
F224 = PRIVATE / "f224-device-bound"
F222_BASE = "openmitrastar-linux510-f222-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
F224_BASE = "openmitrastar-linux510-f224-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_contract_is_machine_readable_and_ui_driven() -> None:
    radioctl = (FOUNDATION / "overlay/usr/sbin/om-radioctl").read_text(encoding="utf-8")
    app = (FOUNDATION / "overlay/www/app.js").read_text(encoding="utf-8")
    html = (FOUNDATION / "overlay/www/dashboard.html").read_text(encoding="utf-8")
    assert "lyoko.radio.settings/v1" in radioctl
    assert "settings_json" in radioctl
    assert '"allowed_values":[1,2,3,4,5,6,7,8,9,10,11,12,13]' in radioctl
    assert '"allowed_values":[36,40,44,48]' in radioctl
    assert '"candidate_values":[52,56,60,64,100,104,108,112]' in radioctl
    assert "applyRadioSettingsContract" in app
    assert "allowedValuesText" in app
    assert html.count('data-setting="') >= 16


def test_built_f224_preserves_f222_kernel_layout_and_private_identity() -> None:
    manifest_path = F224 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    parent = json.loads((F222 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f224-radio-settings-contract/v1"
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["radio_settings_contract"]["secrets_returned"] is False
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F224 / f"{F224_BASE}{suffix}") == sha256(F222 / f"{F222_BASE}{suffix}")
    assert manifest["layout"]["mtd_mapping"] == parent["layout"]["mtd_mapping"]
    assert manifest["storage"] == parent["storage"]
