from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f213_movistar_f1_ui as f213  # noqa: E402


def test_frozen_movistar_f1_ui_contract() -> None:
    overlay = f213.OVERLAY
    html = (overlay / "www/dashboard.html").read_text(encoding="utf-8")
    js = (overlay / "www/app.js").read_text(encoding="utf-8")
    login = (overlay / "www/login.html").read_text(encoding="utf-8")
    assert "/assets/movistar-logo.svg" in html and "/assets/telefonica-logo.svg" in html
    assert "wifi-workbench" in html and 'id="setting-inspector"' in html
    assert "Canal automático" in html and "Potencia TX" in html and "DFS / CAC" in html
    assert "settingHelp" in js and "selectRadio" in js and "showSetting" in js
    assert "Mira debajo del router" in login
    assert not (overlay / "usr/share/openmitrastar/device-identity/web_password.sha256").exists()


def test_built_f213_contract() -> None:
    manifest_path = f213.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f213.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f213-movistar-f1-ui/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["frontend"]["ui_version"] == "3.0.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-3.0-f213"
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["storage"]["store_erased_ff"] is True
    assert manifest["storage"]["candidate_ends_before_store"] is True
    assert manifest["spi_probe"]["write"] is False
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "etc/init.d/S43-web-credential" in changed
    assert "www/dashboard.html" in changed
    assert "www/app.js" in changed
    assert "www/app.css" in changed
    assert "www/login.html" in changed
    assert "www/login.css" in changed
    assert "www/assets/movistar-logo.svg" in changed
    assert "www/assets/router-label-help-sanitized.jpg" in changed
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"
    assert manifest["runtime_signature_verifier"]["sha256"] == "831ea6de598834222c6e6e597b13f297aeaf5d472a55de0a7535419e978442b7"


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f213.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
