from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f176_lyoko_package_ui as f176  # noqa: E402


def test_source_has_read_only_package_ui() -> None:
    api = (f176.OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    app = (f176.OVERLAY / "www/app.js").read_text(encoding="utf-8")
    html = (f176.OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    assert "packages)" in api
    assert '"runtime_install_enabled":%s' in api
    assert "/api/v1/packages" in app
    assert 'id="packages"' in html
    package_case = api[api.index("packages)"):api.index("radios/2g/stage")]
    for forbidden in ("opkg install", "opkg remove", "rm -rf", "wget ", "mtd_debug", "mount -o rw"):
        assert forbidden not in package_case


def test_built_contract() -> None:
    manifest_path = f176.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f176.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f176-lyoko-package-ui/v1"
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["package_state"] == source["package_state"]
    inventory = manifest["foundation_assets"]["rootfs_diff"]
    changed_files = {
        path for path in inventory["changed_paths"]
        if inventory["new"][path]["type"] == "file"
    }
    assert changed_files == {
        "etc/openmitrastar/release",
        "usr/libexec/openmitrastar/om-api-v1",
        "www/api/v1/packages",
        "www/app.js",
        "www/dashboard.html",
        "www/layout-fixes.css",
    }
