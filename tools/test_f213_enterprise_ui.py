from __future__ import annotations

import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-3.0-f213"
OVERLAY = FOUNDATION / "overlay"
CGI = FOUNDATION / "overlay/usr/libexec/openmitrastar/om-oem-cgi"
PROVISION = FOUNDATION / "overlay/etc/init.d/S43-web-credential"
WSL_ROOT = "/workspace/user-home/Desktop/MitraStar"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def run_wsl(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def test_movistar_f1_openwrt_shell_is_present() -> None:
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    css = (OVERLAY / "www/app.css").read_text(encoding="utf-8")
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    for marker in (
        "/assets/movistar-logo.svg", "/assets/telefonica-logo.svg", "wifi-workbench",
        'data-radio-target="2g"', 'data-radio-target="5g"', 'id="setting-inspector"',
        'id="coverage-radar"', "Canal automático", "Potencia TX", "DFS / CAC",
    ):
        assert marker in html
    for marker in ("settingHelp", "selectRadio", "selectConfigPane", "showSetting", "updateCoverage"):
        assert marker in js
    for marker in (".band-button.active", ".config-field.setting-selected", ".setting-inspector", "@keyframes radar-spin"):
        assert marker in css


def test_login_uses_new_logos_and_sanitized_original_asset() -> None:
    html = (OVERLAY / "www/login.html").read_text(encoding="utf-8")
    css = (OVERLAY / "www/login.css").read_text(encoding="utf-8")
    assets = OVERLAY / "www/assets"
    assert "/assets/movistar-logo.svg" in html
    assert "/assets/telefonica-logo.svg" in html
    assert "/assets/router-label-help-sanitized.jpg" in html
    assert "Mira debajo del router" in html
    assert "Una credencial, toda la consola" in html
    assert "login-layout" in css and "device-guide" in css
    assert not (assets / "router-label-help.jpg").exists()
    assert not (assets / "router-oem-outline.jpg").exists()
    assert not (assets / "movistar-oem-logo.png").exists()


def test_generic_foundation_contains_no_provisioned_web_password() -> None:
    assert not (OVERLAY / "usr/share/openmitrastar/device-identity/web_password.sha256").exists()
    source = PROVISION.read_text(encoding="utf-8")
    assert "device-identity/web_password.sha256" in source
    assert "chmod 0600" in source
    assert "state=unprovisioned" in source


def test_web_credential_provisioning_is_hash_only_and_mode_600() -> None:
    root = f"/tmp/lyoko-web-credential-{hashlib.sha256(b'provision-test').hexdigest()[:12]}"
    source = f"{root}/source.sha256"
    target = f"{root}/secrets/web.password.sha256"
    state = f"{root}/state"
    test_hash = hashlib.sha256(b"offline-test-password").hexdigest()
    try:
        setup = run_wsl(f"rm -rf {root}; mkdir -p {root}; printf '%s\\n' {test_hash} >{source}; chmod 0600 {source}")
        assert setup.returncode == 0, setup.stderr
        command = (
            f"OM_WEB_PROVISIONED_HASH={source} "
            f"OM_SECRETS_ROOT={root}/secrets "
            f"OM_WEB_PASSWORD_HASH_FILE={target} "
            f"OM_WEB_CREDENTIAL_STATE={state} "
            f"sh {shlex.quote(f'{WSL_ROOT}/versions/lyoko-foundation-3.0-f213/overlay/etc/init.d/S43-web-credential')}"
        )
        result = run_wsl(command)
        assert result.returncode == 0, result.stderr
        evidence = run_wsl(f"cat {target}; cat {state}; stat -c %a {target}")
        lines = evidence.stdout.splitlines()
        assert lines == [test_hash, "state=ready", "source=device-bound-hash", "600"]
    finally:
        run_wsl(f"rm -rf {root}")


def test_login_rate_limit_and_successful_session() -> None:
    root = f"/tmp/lyoko-login-{hashlib.sha256(b'login-test').hexdigest()[:12]}"
    hash_file = f"{root}/web.password.sha256"
    test_hash = hashlib.sha256(b"offline-test-password").hexdigest()
    try:
        setup = run_wsl(f"rm -rf {root}; mkdir -p {root}; printf '%s\\n' {test_hash} >{hash_file}; chmod 0600 {hash_file}")
        assert setup.returncode == 0, setup.stderr
        cgi = f"{WSL_ROOT}/versions/lyoko-foundation-3.0-f213/overlay/usr/libexec/openmitrastar/om-oem-cgi"
        common = (
            f"OM_WEB_PASSWORD_HASH_FILE={hash_file} "
            f"OM_WEB_RUN_ROOT={root}/run "
            f"OM_WEB_ROOT={shlex.quote(f'{WSL_ROOT}/versions/lyoko-foundation-3.0-f213/overlay/www')} "
            "OM_WEB_REMOTE_ADDR=192.0.2.10 OM_WEB_AUTH_DELAY=0 OM_WEB_AUTH_MAX_FAILURES=3 "
            "OM_WEB_AUTH_LOCK_SECONDS=60 OM_WEB_NOW=1000 REQUEST_METHOD=POST "
            "CONTENT_TYPE=application/x-www-form-urlencoded "
        )
        wrong_body = "login_password=wrong"
        outputs = []
        for _ in range(3):
            outputs.append(run_wsl(
                f"printf %s {shlex.quote(wrong_body)} | {common} CONTENT_LENGTH={len(wrong_body)} sh {shlex.quote(cgi)} index.cgi"
            ).stdout)
        assert "Status: 403 Forbidden" in outputs[0]
        assert "Status: 429 Too Many Requests" in outputs[2]
        assert "Retry-After: 60" in outputs[2]

        good_body = "login_password=offline-test-password"
        locked = run_wsl(
            f"printf %s {shlex.quote(good_body)} | {common} CONTENT_LENGTH={len(good_body)} sh {shlex.quote(cgi)} index.cgi"
        )
        assert "Status: 429 Too Many Requests" in locked.stdout

        unlocked_common = common.replace("OM_WEB_NOW=1000", "OM_WEB_NOW=1061")
        success = run_wsl(
            f"printf %s {shlex.quote(good_body)} | {unlocked_common} CONTENT_LENGTH={len(good_body)} "
            f"OM_WEB_SESSION_TOKEN={'a' * 64} sh {shlex.quote(cgi)} index.cgi"
        )
        assert success.returncode == 0, success.stderr
        assert "Status: 302 Found" in success.stdout
        assert "Location: /dashboard.html" in success.stdout
        assert "HttpOnly; SameSite=Strict" in success.stdout
    finally:
        run_wsl(f"rm -rf {root}")
