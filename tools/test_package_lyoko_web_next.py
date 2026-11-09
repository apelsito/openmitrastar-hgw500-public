from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import shutil

import pytest
from package_lyoko_web_next import DIST, package, validate_dist


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/package_lyoko_web_next.py"
F314_MANIFEST = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f314-device-bound/manifest.json"
F314_BUILDER = ROOT / "tools/build_f314_qtn_nondfs_guard_from_f313.py"
AUTH_BUILDER = ROOT / "tools/build_f309_authenticated_dashboard_from_f306.py"


def test_source_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "/usr/share/openmitrastar/web/dashboard.html" in source
    assert "/www/assets/lyoko-next" in source
    assert "existing-omsession-cgi" in source
    assert '"firmware_generated": False' in source
    assert '"mtd_writes": False' in source
    assert '"radio_mutation": False' in source


def test_package_is_reproducible_and_safe() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-web-next-") as directory:
        first = Path(directory) / "first"
        second = Path(directory) / "second"
        for output in (first, second):
            result = subprocess.run(
                ["python", str(SCRIPT), "--output", str(output)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            assert result.returncode == 0, result.stderr or result.stdout

        one = json.loads((first / "manifest.json").read_text(encoding="ascii"))
        two = json.loads((second / "manifest.json").read_text(encoding="ascii"))
        assert one == two
        assert one["safety"] == {
            "firmware_generated": False,
            "flash": False,
            "hardware_actions": False,
            "mtd_writes": False,
            "radio_mutation": False,
        }
        assert one["integration"]["required_api"] == ["status", "firmware", "radios/2g", "radios/5g"]
        assert "optimization" in one["integration"]["optional_api"]
        dashboard = first / "overlay/usr/share/openmitrastar/web/dashboard.html"
        assert dashboard.is_file()
        html = dashboard.read_text(encoding="utf-8")
        assert "./assets/" not in html
        assert "/assets/lyoko-next/" in html
        assert not (first / "overlay/www/dashboard.html").exists()
        assert one["release_eligible"] is False and one["flash_supported"] is False
        assert one["integration"]["emulator_backend_packaged"] is False
        paths = {item["path"] for item in one["files"]}
        assert {"www/assets/movistar-logo.svg", "www/assets/telefonica-logo.svg", "www/assets/movistar-m.png"}.issubset(paths)
        assert len([path for path in paths if path.endswith(".js")]) >= 2
        assert '/assets/movistar-m.png' in html
        assert '/assets/lyoko-next/movistar-m.png' not in html
        assert package(first)[2] is True


def test_branding_tampering_and_unrecognized_assets_are_rejected(tmp_path):
    dist = tmp_path / "dist"
    shutil.copytree(DIST, dist)
    logo = dist / "assets/movistar-logo.svg"
    original = logo.read_bytes()
    logo.write_bytes(b"changed")
    with pytest.raises(ValueError, match="branding changed"):
        validate_dist(dist)
    logo.write_bytes(original)
    (dist / "assets/unknown.js").write_bytes(b"not a hashed bundle")
    with pytest.raises(ValueError, match="unrecognized"):
        validate_dist(dist)


def test_external_entry_reference_is_rejected(tmp_path):
    dist = tmp_path / "dist"
    shutil.copytree(DIST, dist)
    index = dist / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("./assets/", "https://example.invalid/"), encoding="utf-8")
    with pytest.raises(ValueError, match="external asset"):
        validate_dist(dist)


def test_preexisting_staging_sibling_is_never_deleted(tmp_path):
    output = tmp_path / "test-package"
    sibling = tmp_path / ".test-package.staging"
    sibling.mkdir()
    sentinel = sibling / "keep.txt"
    sentinel.write_text("user-owned")
    package(output)
    assert sentinel.read_text() == "user-owned"


def test_f314_authenticated_dashboard_contract_is_preserved() -> None:
    manifest = json.loads(F314_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["web_security"]["authenticated_dashboard"] == "/dashboard.cgi"
    assert manifest["web_security"]["public_dashboard_html"] is False
    f314 = F314_BUILDER.read_text(encoding="utf-8")
    auth = AUTH_BUILDER.read_text(encoding="utf-8")
    assert '"www/dashboard.cgi"' in f314
    assert '"usr/libexec/openmitrastar/om-oem-cgi"' in f314
    assert "require_page_session || exit 0; render_management_page" in auth
    assert "cat /usr/share/openmitrastar/web/dashboard.html" in auth
