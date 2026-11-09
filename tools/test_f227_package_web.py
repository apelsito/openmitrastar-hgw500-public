from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-4.0-f227"
API = FOUNDATION / "overlay/usr/libexec/openmitrastar/om-api-v1"
MANAGER = FOUNDATION / "overlay/usr/bin/lyoko-pkg"
CONTROL = FOUNDATION / "overlay/usr/sbin/om-package-api"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def run_wsl(script: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", script],
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def payload(stdout: str) -> dict:
    return json.loads(stdout.replace("\r\n", "\n").split("\n\n", 1)[-1])


def test_package_names_reject_dot_and_path_like_values() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f227-name-") as directory:
        root = Path(directory)
        pkgbox = root / "pkgbox"
        pkgbox.write_bytes(b'#!/bin/sh\ncmd=$1\nshift\nexec "$cmd" "$@"\n')
        pkgbox.chmod(0o755)
        env = f"LYOKO_PKGBOX={shlex.quote(wsl_path(pkgbox))} LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f227-name "
        for name in (".", "..", "-option", "bad/name", "A"):
            result = run_wsl(env + f"sh {shlex.quote(wsl_path(MANAGER))} install {shlex.quote(name)}")
            assert result.returncode != 0
            assert "invalid-package-name" in result.stderr


def test_package_api_is_feature_gated_and_sanitizes_results() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f227-api-") as directory:
        root = Path(directory)
        feature = root / "package-api-v1"
        manager = root / "lyoko-pkg"
        lock = root / "package.lock"
        manager.write_bytes(
            b'#!/bin/sh\ncase "$1" in\n'
            b'plan) printf "%s\\n" "$2";;\n'
            b'install) printf "LYOKO_PKG_INSTALL_PASS package=%s version=1.0.0-1 root=/run/lyoko-packages/pkgs/%s persistence=volatile\\n" "$2" "$2";;\n'
            b'remove) printf "LYOKO_PKG_REMOVE_PASS package=%s persistence=volatile\\n" "$2";;\n'
            b'update) printf "LYOKO_PKG_UPDATE_PASS packages=1\\n";;\n'
            b'*) exit 2;;\nesac\n'
        )
        chmod = run_wsl(f"chmod 755 {shlex.quote(wsl_path(manager))}")
        assert chmod.returncode == 0, chmod.stderr
        base = (
            f"OM_API_AUTH_BYPASS=1 OM_RUN_ROOT={shlex.quote(wsl_path(root / 'run'))} "
            f"OM_PACKAGE_API_FEATURE={shlex.quote(wsl_path(feature))} "
            f"OM_PACKAGE_MANAGER={shlex.quote(wsl_path(manager))} OM_PACKAGE_LOCK={shlex.quote(wsl_path(lock))} "
            "REQUEST_METHOD=POST HTTP_X_OM_CSRF=development "
            "HTTP_X_OM_CONFIRM=OPENMITRASTAR_LYOKO_PKG_INSTALL_V1 "
        )
        body = "action=install&package=lyoko-netdiag"
        disabled = run_wsl(base + f"CONTENT_LENGTH={len(body)} sh {shlex.quote(wsl_path(API))} packages", body)
        assert payload(disabled.stdout)["error"] == "package-api-disabled"
        feature.write_bytes(b"OPENMITRASTAR_PACKAGE_API=1\n")
        installed = run_wsl(base + f"CONTENT_LENGTH={len(body)} sh {shlex.quote(wsl_path(API))} packages", body)
        result = payload(installed.stdout)
        assert result["schema"] == "lyoko.api.package-operation/v1"
        assert result["action"] == "install" and result["package"] == "lyoko-netdiag"
        assert result["persistence"] == "volatile" and result["network_fetch"] is False
        assert "LYOKO_PKG" not in installed.stdout
        invalid_body = "action=remove&package=.."
        invalid_base = base.replace("OPENMITRASTAR_LYOKO_PKG_INSTALL_V1", "OPENMITRASTAR_LYOKO_PKG_REMOVE_V1")
        invalid = run_wsl(invalid_base + f"CONTENT_LENGTH={len(invalid_body)} sh {shlex.quote(wsl_path(API))} packages", invalid_body)
        assert payload(invalid.stdout)["error"] == "invalid-package-request"


def test_web_surface_never_exposes_package_exec_or_remote_fetch() -> None:
    api = API.read_text(encoding="utf-8")
    app = (FOUNDATION / "overlay/www/app.js").read_text(encoding="utf-8")
    assert '"exec_over_http":false' in api
    assert '"endpoint":"/api/v1/packages"' in api
    assert "runPackageAction" in app
    assert "packages-exec" not in api and "package-exec" not in app and "packages-update" not in api
    assert (FOUNDATION / "overlay/etc/openmitrastar/features/package-api-v1").read_text(encoding="ascii").strip() == "OPENMITRASTAR_PACKAGE_API=0"


def test_runtime_feature_override_is_ephemeral_and_reversible() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f227-feature-") as directory:
        root = Path(directory)
        default = root / "default"
        default.write_bytes(b"OPENMITRASTAR_PACKAGE_API=0\n")
        env = f"OM_RUN_ROOT={shlex.quote(wsl_path(root / 'run'))} OM_PACKAGE_API_DEFAULT={shlex.quote(wsl_path(default))} "
        disabled = run_wsl(env + f"sh {shlex.quote(wsl_path(CONTROL))} status")
        assert "state=disabled" in disabled.stdout and "source=default" in disabled.stdout
        enabled = run_wsl(env + f"sh {shlex.quote(wsl_path(CONTROL))} enable")
        assert "state=enabled" in enabled.stdout and "source=runtime" in enabled.stdout
        disabled_again = run_wsl(env + f"sh {shlex.quote(wsl_path(CONTROL))} disable")
        assert "state=disabled" in disabled_again.stdout and "source=default" in disabled_again.stdout
