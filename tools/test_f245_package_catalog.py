from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F243 = PRIVATE / "f243-device-bound"
F245 = PRIVATE / "f245-device-bound"
ROOT = Path(__file__).resolve().parents[1]


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f245_source_contract_is_bounded() -> None:
    foundation = ROOT / "versions/lyoko-foundation-4.9-f245"
    api = (foundation / "overlay/usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    js = (foundation / "overlay/www/app.js").read_text(encoding="utf-8")
    html = (foundation / "overlay/www/dashboard.html").read_text(encoding="utf-8")
    for operation in ("search", "info", "depends", "plan", "update"):
        assert f"view={operation}" in api
    assert '"maintainer_scripts":false' in api
    assert '"network_fetch":false' in api
    assert '"persistent_install":false' in api
    assert 'id="package-search"' in html
    assert 'id="package-inspector"' in html
    assert "packagePlan" in js
    for forbidden in ("wget", "curl", "mtd_debug", "flash_erase", "fw_setenv", "dd of="):
        assert forbidden not in api


def test_f245_preserves_f243_kernel_and_is_hardware_hold() -> None:
    manifest_path = F245 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f245-package-catalog/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["package_catalog"]["api_queries"] == ["search", "info", "depends", "plan", "update"]
    assert manifest["package_catalog"]["network_fetch"] is False
    assert manifest["package_catalog"]["persistent_install"] is False
    assert manifest["package_catalog"]["maintainer_scripts"] is False
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert changed == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/libexec/openmitrastar/om-api-v1",
        "usr/share/openmitrastar/web/dashboard.html",
        "www/app.css",
        "www/app.js",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F245 / artifact("f245", suffix)) == sha256(F243 / artifact("f243", suffix))


def test_f245_builder_has_no_hardware_actions() -> None:
    source = (ROOT / "tools/build_f245_package_catalog.py").read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot", "ssh "):
        assert forbidden not in source
