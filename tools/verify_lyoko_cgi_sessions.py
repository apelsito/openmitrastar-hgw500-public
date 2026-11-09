#!/usr/bin/env python3
"""Run original CGI/API shell scripts in a host-native, minimal Linux chroot.

This does not emulate ARC instructions and does not execute router control tools.
When declared by the package, only the pinned frontend identity API transform is applied.
All credentials and sessions are synthetic and disappear with the test root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlencode


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_response(raw: bytes) -> tuple[int, dict[str, str], bytes]:
    head, separator, body = raw.partition(b"\r\n\r\n")
    if not separator: raise ValueError("CGI response is missing CRLF header termination")
    headers = {}
    for line in head.decode("utf-8").split("\r\n"):
        key, colon, value = line.partition(":")
        if not colon: raise ValueError("invalid CGI header")
        headers[key.lower()] = value.strip()
    return int(headers.get("status", "200").split()[0]), headers, body


def copy_host_tool(root: Path, name: str, source_override: Path | None = None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name): raise ValueError("host tool destination must be a basename")
    found = str(source_override) if source_override else shutil.which(name)
    if not found: raise ValueError(f"host tool missing: {name}")
    source = Path(found)
    destination = root / "bin" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination, follow_symlinks=True)
    dependencies = subprocess.run(["ldd", str(source)], capture_output=True, text=True, check=False)
    if dependencies.returncode and "not a dynamic executable" not in dependencies.stdout + dependencies.stderr:
        raise ValueError(f"cannot resolve dependencies of host {name}")
    for library in re.findall(r"(?:=>\s+)?(/[^\s()]+)", dependencies.stdout):
        path = Path(library)
        if not path.is_file(): raise ValueError(f"missing host library: {path}")
        target = root / str(path).lstrip("/")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target, follow_symlinks=True)


def execute_cases(root: Path, dashboard: bytes) -> list[dict]:
    now = int(time.time())
    address = "192.0.2.17"
    token = "1" * 64
    session_path = root / "run/openmitrastar/web/sessions" / token
    sessions = session_path.parent
    sessions.mkdir(parents=True, exist_ok=True); sessions.chmod(0o700)
    secret = root / "run/openmitrastar/secrets/web.password.sha256"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text(digest(b"lab-only-password") + "\n", encoding="ascii"); secret.chmod(0o600)
    for name, minor in (("null", 3), ("urandom", 9)):
        device = root / "dev" / name; device.parent.mkdir(parents=True, exist_ok=True)
        os.mknod(device, stat.S_IFCHR | 0o666, os.makedev(1, minor))

    def session(expires=None, bound=address):
        session_path.write_text(f"expires={now + 900 if expires is None else expires}\naddr_sha256={digest(bound.encode())}\ncsrf={'2' * 64}\n", encoding="ascii")
        session_path.chmod(0o600)

    def invoke(endpoint="dashboard.cgi", cookie="", method="GET", body=None, api=False, overrides=None):
        encoded = urlencode(body or {}).encode("ascii")
        env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "REQUEST_METHOD": method,
               "HTTP_COOKIE": cookie, "REMOTE_ADDR": address, "CONTENT_TYPE": "application/x-www-form-urlencoded",
               "CONTENT_LENGTH": str(len(encoded)), "OM_WEB_NOW": str(now), "OM_WEB_AUTH_DELAY": "0",
               "OM_WEB_AUTH_MAX_FAILURES": "3", "OM_WEB_SESSION_TOKEN": "3" * 64}
        env.update(overrides or {})
        script = "/usr/libexec/openmitrastar/om-api-v1" if api else "/usr/libexec/openmitrastar/om-oem-cgi"
        process = subprocess.run([shutil.which("chroot"), str(root), "/bin/sh", script, endpoint],
                                 input=encoded, capture_output=True, env=env, timeout=5)
        if process.returncode: raise ValueError(f"CGI execution failed for {endpoint}: rc={process.returncode}, stderr={process.stderr.decode(errors='replace')[:200]}")
        return parse_response(process.stdout)

    results = []
    def record(name, condition):
        if not condition: raise ValueError(f"CGI session test failed: {name}")
        results.append({"name": name, "status": "PASS"})

    status, headers, body = invoke()
    record("anonymous-dashboard-redirect", status == 302 and headers.get("location") == "/index.cgi" and not body)
    status, _, _ = invoke(cookie="OMSESSION=" + token)
    record("unknown-session-rejected", status == 302)
    session()
    status, headers, body = invoke(cookie="OMSESSION=" + token)
    record("valid-session-exact-new-dashboard", status == 200 and body == dashboard)
    record("dashboard-security-headers", headers.get("cache-control") == "no-store" and headers.get("x-content-type-options") == "nosniff"
           and "script-src 'self'" in headers.get("content-security-policy", ""))
    session(bound="192.0.2.18")
    record("wrong-client-rejected", invoke(cookie="OMSESSION=" + token)[0] == 302)
    session(expires=now - 1)
    record("expired-session-rejected-and-removed", invoke(cookie="OMSESSION=" + token)[0] == 302 and not session_path.exists())
    session(expires="not-a-number")
    record("malformed-expiry-rejected", invoke(cookie="OMSESSION=" + token)[0] == 302 and not session_path.exists())
    sentinel = root / "run/openmitrastar/sentinel"; sentinel.write_text("keep", encoding="ascii")
    record("invalid-cookie-cannot-traverse", invoke(cookie="OMSESSION=../../sentinel")[0] == 302 and sentinel.read_text() == "keep")
    record("dashboard-post-disallowed", invoke(method="POST")[0] == 405)
    status, _, body = invoke(endpoint="status", api=True)
    record("anonymous-api-rejected-before-runtime-tools", status == 403 and json.loads(body).get("error") == "auth")
    session()
    status, _, body = invoke(endpoint="session", api=True, cookie="OMSESSION=" + token)
    record("authenticated-api-session", status == 200 and json.loads(body).get("authenticated") is True)
    bundle_path = root / "etc/lyoko/web-next.json"
    if bundle_path.exists():
        bundle = json.loads(bundle_path.read_text(encoding="ascii"))
        record("anonymous-frontend-identity-rejected", invoke(endpoint="frontend", api=True)[0] == 403)
        status, _, body = invoke(endpoint="frontend", api=True, cookie="OMSESSION=" + token)
        identity = json.loads(body)
        record("authenticated-frontend-matches-active-bundle", status == 200 and identity.get("bundle") == bundle
               and identity.get("ui_version") == bundle["ui_version"] and identity.get("build_id") == bundle["build_id"]
               and identity.get("asset_layout") == "split-v1"
               and identity.get("assets", {}).get("dashboard_html_sha256") == digest(dashboard))

    status, headers, _ = invoke(endpoint="index.cgi", method="POST", body={"login_password": "lab-only-password"}, overrides={"HTTPS": "on"})
    cookie = headers.get("set-cookie", "")
    record("login-creates-secure-session", status == 302 and headers.get("location") == "/dashboard.cgi"
           and all(value in cookie for value in ("OMSESSION=", "HttpOnly", "SameSite=Strict", "Secure")))
    login_cookie = cookie.split(";", 1)[0]
    record("new-session-opens-exact-dashboard", invoke(cookie=login_cookie)[2] == dashboard)
    status, headers, _ = invoke(endpoint="logout.cgi", cookie=login_cookie)
    record("logout-invalidates-session", status == 302 and "Max-Age=0" in headers.get("set-cookie", "") and invoke(cookie=login_cookie)[0] == 302)
    record("wrong-password-rejected", invoke(endpoint="index.cgi", method="POST", body={"login_password": "wrong"})[0] == 403)
    invoke(endpoint="index.cgi", method="POST", body={"login_password": "wrong"})
    status, headers, _ = invoke(endpoint="index.cgi", method="POST", body={"login_password": "wrong"})
    record("repeated-failure-rate-limited", status == 429 and int(headers.get("retry-after", "0")) > 0)
    return results


def linux_worker(args):
    from lyoko_web_rootfs_worker import sha256, validate_overlay
    if os.geteuid() != 0: raise ValueError("the isolated chroot requires the Linux builder's root user")
    if sha256(args.rootfs) != args.rootfs_sha256: raise ValueError("pinned rootfs changed")
    manifest = json.loads((args.package / "manifest.json").read_text(encoding="ascii"))
    validate_overlay(args.package / "overlay", manifest)
    if args.report.exists(): raise ValueError("refusing to overwrite evidence")
    scripts = {}
    for name in ("om-oem-cgi", "om-api-v1"):
        scripts[name] = subprocess.run(["unsquashfs", "-cat", str(args.rootfs), "usr/libexec/openmitrastar/" + name], check=True, capture_output=True).stdout
    source_script_hashes = {name: digest(data) for name, data in scripts.items()}
    transforms = []
    if manifest.get("transforms"):
        from lyoko_frontend_identity import transform_bytes
        scripts["om-api-v1"], audit = transform_bytes(scripts["om-api-v1"], manifest["transforms"][0])
        transforms.append(audit)
    dashboard = (args.package / "overlay/usr/share/openmitrastar/web/dashboard.html").read_bytes()
    with tempfile.TemporaryDirectory(prefix="lyoko-cgi-sessions-", dir="/tmp") as directory:
        root = Path(directory)
        for command in ("sh", "cat", "sed", "head", "cut", "sha256sum", "rm", "awk", "date", "id", "ls", "mkdir", "chmod", "mv", "dd", "sleep", "tr", "wc"):
            copy_host_tool(root, command)
        for name, data in scripts.items():
            target = root / "usr/libexec/openmitrastar" / name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        page = root / "usr/share/openmitrastar/web/dashboard.html"
        page.parent.mkdir(parents=True, exist_ok=True); page.write_bytes(dashboard)
        for relative in ("etc/lyoko/frontend.env", "etc/lyoko/web-next.json"):
            source = args.package / "overlay" / relative
            if source.is_file():
                target = root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source.read_bytes())
        results = execute_cases(root, dashboard)
        if any((root / "usr/libexec/openmitrastar" / name).read_bytes() != data for name, data in scripts.items()):
            raise ValueError("tested script changed")
    report = {"schema": "lyoko.cgi-session-host-test/v2", "status": "PASS", "base": args.base,
              "source_rootfs_sha256": args.rootfs_sha256, "scripts": {name: digest(data) for name, data in scripts.items()},
              "source_scripts": source_script_hashes, "api_transforms": transforms,
              "dashboard_sha256": digest(dashboard), "overlay_manifest_sha256": sha256(args.package / "manifest.json"),
              "tests": results, "execution": "original CGI and API with only declared pinned identity transform; host-native sh in a minimal Linux chroot",
              "not_proven": ["ARC binary execution", "mini_httpd HTTP/TLS behavior", "browser session integration", "radio hardware"],
              "hardware_actions": False, "real_credentials_used": False, "release_eligible": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps({"status": "PASS", "base": args.base, "tests": len(results), "report": str(args.report), "execution": report["execution"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", choices=("f314", "f317"), default="f314")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--linux-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--rootfs", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--rootfs-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.linux_worker:
        linux_worker(args)
    else:
        import shlex
        from verify_lyoko_web_next_f314_rootfs import BASES
        from package_lyoko_web_next import default_package_dir
        from build_f306_unified_product_from_f305 import run_wsl, wsl_path
        package = (args.package or default_package_dir()).resolve()
        report = (args.report or package / f"cgi-sessions-isolated-{args.base}.json").resolve()
        base = BASES[args.base]
        argv = ["python3", wsl_path(Path(__file__).resolve()), "--linux-worker", "--base", args.base,
                "--package", wsl_path(package), "--report", wsl_path(report), "--rootfs", wsl_path(base["rootfs"]), "--rootfs-sha256", base["sha256"]]
        print(run_wsl(shlex.join(argv), args.distro))


if __name__ == "__main__": main()
