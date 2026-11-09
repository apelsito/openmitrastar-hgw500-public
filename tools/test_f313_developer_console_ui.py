from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "versions/lyoko-foundation-6.7.7-f312-http11-transaction-compat"
F313 = ROOT / "versions/lyoko-foundation-6.8.0-f313-developer-console-ui"
OVERLAY = F313 / "overlay"
HTML = OVERLAY / "usr/share/openmitrastar/web/dashboard.html"
JS = OVERLAY / "www/app.js"
CSS = OVERLAY / "www/f313-console.css"
ENV = OVERLAY / "etc/lyoko/frontend.env"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env_values() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in ENV.read_text(encoding="ascii").splitlines()
        if "=" in line
    )


def test_f313_is_an_isolated_frontend_only_fork() -> None:
    assert F313.is_dir()
    assert sha256(OVERLAY / "usr/libexec/openmitrastar/om-api-v1") == sha256(
        BASE / "overlay/usr/libexec/openmitrastar/om-api-v1"
    )
    assert sha256(F313 / "emulator/server.py") == sha256(BASE / "emulator/server.py")
    assert (F313 / "F313_UI_SCOPE.md").is_file()


def test_console_is_developer_only_and_keeps_complete_navigation() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'content="6.8.0"' in html
    assert '<body class="developer-only">' in html
    assert "mode-switcher" not in html
    assert "mode-button" not in html
    assert ">Normal<" not in html
    assert ">Advanced<" not in html
    assert html.count('class="section-link') == 11
    for route in (
        "#developer/home",
        "#developer/wifi/2g",
        "#developer/wifi/5g",
        "#developer/network/network-local",
        "#developer/network/network-services",
        "#developer/network/network-clients",
        "#developer/system/hardware-panel",
        "#developer/system/storage-panel",
        "#developer/system/packages-panel",
        "#developer/system/firmware-panel",
        "#developer/diagnostics",
    ):
        assert route in html


def test_profiles_and_actionable_inspector_are_complete() -> None:
    html = HTML.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    for profile in ("home", "iot", "performance", "stability"):
        assert f'data-profile="{profile}"' in html
        assert re.search(rf"\n\s*{profile}: \{{", js)
    for label in ("Casa", "Domótica", "Rendimiento", "Estabilidad"):
        assert label in html
    for element_id in (
        "setting-current",
        "setting-values",
        "setting-recommended",
        "setting-lower",
        "setting-higher",
        "setting-operational",
        "setting-support",
        "setting-how",
        "setting-source",
        "setting-apply",
        "setting-risk",
    ):
        assert f'id="{element_id}"' in html
    for marker in (
        'const fixedMode = "developer"',
        "profileAssessment",
        "previewable",
        "loadSelectedProfile",
        "setting.writable === true",
        "renderFieldStates",
        "operationalState",
        "configurationGuide",
        "valores se cargarán como plan sin escritura",
        "Simulación 5 GHz",
        "qtn-setting-material-change-not-certified",
    ):
        assert marker in js


def test_state_and_editability_are_visually_separate() -> None:
    css = CSS.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert "field-state-stack" in css
    assert "operationalState(setting)" in js
    assert "support-badge ${esc(editability.className)}" in js
    assert "Estado operativo" in HTML.read_text(encoding="utf-8")
    assert "Editabilidad" in HTML.read_text(encoding="utf-8")
    assert ".support-badge.pending" in css
    assert ".support-badge.firmware" in css


def test_layout_is_responsive_and_respects_ui_constraints() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 820px)" in css
    assert "@media (max-width: 560px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert not re.search(r"font-size\s*:\s*[^;]*(vw|vh)", css)
    assert not re.search(r"letter-spacing\s*:\s*-", css)
    radii = [int(value) for value in re.findall(r"border-radius\s*:\s*(\d+)px", css)]
    assert radii and max(radii) <= 8


def test_frontend_identity_covers_f313_assets() -> None:
    env = env_values()
    assert env["LYOKO_UI_VERSION"] == "6.8.0"
    assert env["LYOKO_UI_SOURCE"] == "lyoko-foundation-6.8.0-f313-developer-console-ui"
    assert env["LYOKO_UI_DASHBOARD_HTML_SHA256"] == sha256(HTML)
    assert env["LYOKO_UI_APP_JS_SHA256"] == sha256(JS)
    assert env["LYOKO_UI_F313_CSS_SHA256"] == sha256(CSS)
    assert re.fullmatch(r"[0-9a-f]{16}", env["LYOKO_UI_BUILD_ID"])


def test_emulator_web_copy_is_synchronized() -> None:
    web = F313 / "emulator/web"
    assert sha256(web / "dashboard.html") == sha256(HTML)
    assert sha256(web / "app.js") == sha256(JS)
    assert sha256(web / "f313-console.css") == sha256(CSS)


def test_javascript_parses() -> None:
    result = subprocess.run(
        ["node", "--check", str(JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
