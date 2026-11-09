#!/usr/bin/env python3
"""Loopback HTTP integration using F314's server source and real CGI scripts.

Native host execution is not ARC execution or a TLS/hardware acceptance test.
"""
from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPConnection, HTTPSConnection
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlencode

SERVER_C_SHA = "2cb631c81a383b32d4cb4553dfb88f87e8d2593e743f5a1887ed210d4d747440"
ARC_SERVER_SHA = "36c070f942ec1cd5d3260fcee86503242ffe15b5e98728d8a9bf5a1c425d9b16"


def digest(data): return hashlib.sha256(data).hexdigest()


def member(image, path):
    return subprocess.run(["unsquashfs", "-cat", str(image), path], check=True, capture_output=True).stdout


def write(root, relative, data, mode=0o644):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data); target.chmod(mode)


def native_server(source, output):
    if digest((source / "mini_httpd.c").read_bytes()) != SERVER_C_SHA: raise ValueError("mini_httpd source hash mismatch")
    inputs = ["mini_httpd.c", "match.c", "tdate_parse.c", "version.h", "port.h", "match.h", "tdate_parse.h", "mime_encodings.txt", "mime_types.txt", "Makefile"]
    build = output.parent / "server-source"; build.mkdir()
    hashes = {}
    for name in inputs:
        data = (source / name).read_bytes(); (build / name).write_bytes(data); hashes[name] = digest(data)
    commands = [["make", "-s", "-C", str(build), "mime_encodings.h", "mime_types.h"],
                ["gcc", "-std=gnu99", "-O2", "-DNO_IPV6", "-o", str(output), str(build / "mini_httpd.c"), str(build / "match.c"), str(build / "tdate_parse.c"), "-lcrypt"]]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode: raise ValueError(f"host server build failed: {result.stderr[-3000:]}")
    return hashes


class References(HTMLParser):
    def __init__(self): super().__init__(); self.urls = set()
    def handle_starttag(self, tag, attrs):
        if tag in {"img", "script", "link"}:
            self.urls.update(value.split("?", 1)[0] for key, value in attrs if key in {"href", "src"} and value and value.startswith("/"))


def run_http_cases(port, root, manifest, tls_context=None):
    tests = []
    def request(path, body=None, cookie=None, headers=None):
        conn = HTTPSConnection("127.0.0.1", port, timeout=5, context=tls_context) if tls_context else HTTPConnection("127.0.0.1", port, timeout=5)
        effective = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie: effective["Cookie"] = cookie
        effective.update(headers or {})
        conn.request("GET" if body is None else "POST", path, body=urlencode(body or {}), headers=effective)
        response = conn.getresponse()
        result = response.status, {key.lower(): value for key, value in response.getheaders()}, response.read()
        conn.close(); return result
    def record(name, passed):
        if not passed: raise ValueError(f"HTTP integration failed: {name}")
        tests.append({"name": name, "status": "PASS"})

    status, headers, _ = request("/dashboard.cgi")
    record("anonymous-dashboard-redirect", status == 302 and headers.get("location") == "/index.cgi")
    record("no-public-dashboard-bypass", request("/dashboard.html")[0] == 404)
    record("anonymous-api-denied", request("/api/v1/frontend")[0] == 403)
    status, _, body = request("/index.cgi")
    record("login-page-served", status == 200 and b"login_password" in body)
    status, headers, _ = request("/index.cgi", {"login_password": "lab-only-password"})
    set_cookie = headers.get("set-cookie", "")
    record("login-http-cookie", status == 302 and headers.get("location") == "/dashboard.cgi" and "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie)
    if tls_context: record("https-cookie-secure", "Secure" in set_cookie)
    cookie = set_cookie.split(";", 1)[0]
    status, headers, body = request("/dashboard.cgi", cookie=cookie)
    expected_html = (root / "usr/share/openmitrastar/web/dashboard.html").read_bytes()
    record("authenticated-dashboard-exact-bytes", status == 200 and body == expected_html)
    record("csp-and-cache-headers", headers.get("cache-control") == "no-store" and "script-src 'self'" in headers.get("content-security-policy", ""))
    for row in manifest["files"]:
        if not row["path"].startswith("www/assets/"): continue
        url = "/" + row["path"].removeprefix("www/")
        status, headers, body = request(url, cookie=cookie)
        record("asset-hash:" + url, status == 200 and digest(body) == row["sha256"])
        mime = headers.get("content-type", "").split(";", 1)[0].lower()
        if url.endswith(".js"):
            record("module-mime:" + url, mime in {"application/javascript", "text/javascript", "application/x-javascript", "text/ecmascript"})
        elif url.endswith(".css"): record("stylesheet-mime", mime == "text/css")
    status, _, body = request("/api/v1/frontend", cookie=cookie)
    identity = json.loads(body)
    bundle = json.loads((root / "etc/lyoko/web-next.json").read_text())
    record("frontend-identity-through-http", status == 200 and identity.get("bundle") == bundle and identity.get("build_id") == manifest["build_id"])
    status, _, body = request("/api/v1/session", cookie=cookie)
    record("session-through-http", status == 200 and json.loads(body).get("authenticated") is True)
    status, _, body = request("/__csrf_probe.cgi", headers={"X-OM-CSRF": "host-probe-token"})
    record("server-preserves-csrf-header", status == 200 and body.strip() == b"host-probe-token")
    status, headers, _ = request("/logout.cgi", cookie=cookie)
    record("logout-through-http", status == 302 and "Max-Age=0" in headers.get("set-cookie", ""))
    record("session-invalid-after-logout", request("/dashboard.cgi", cookie=cookie)[0] == 302 and request("/api/v1/session", cookie=cookie)[0] == 403)
    return tests


def linux_worker(args):
    from lyoko_web_rootfs_worker import sha256, validate_overlay, apply_overlay, apply_identity_transform
    from verify_lyoko_cgi_sessions import copy_host_tool
    if os.geteuid() != 0: raise ValueError("host chroot requires builder root")
    if sha256(args.rootfs) != args.rootfs_sha256: raise ValueError("pinned rootfs changed")
    if digest(member(args.rootfs, "usr/sbin/mini_httpd")) != ARC_SERVER_SHA: raise ValueError("runtime server does not match source provenance")
    manifest = json.loads((args.package / "manifest.json").read_text())
    expected = validate_overlay(args.package / "overlay", manifest)
    if args.report.exists(): raise ValueError("refusing to overwrite HTTP evidence")
    with tempfile.TemporaryDirectory(prefix="lyoko-http-", dir="/tmp") as directory:
        scratch = Path(directory); root = scratch / "root"; root.mkdir()
        binary = scratch / "mini_httpd"
        sources = native_server(args.server_source, binary)
        for tool in ("sh", "cat", "sed", "head", "cut", "sha256sum", "rm", "awk", "date", "id", "ls", "mkdir", "chmod", "mv", "dd", "sleep", "tr", "wc"):
            copy_host_tool(root, tool)
        copy_host_tool(root, "mini_httpd", binary)
        (root / "bin/ash").symlink_to("sh")
        write(root, "etc/passwd", b"root:x:0:0:root:/root:/bin/sh\n")
        write(root, "etc/group", b"root:x:0:\n")
        write(root, "etc/nsswitch.conf", b"passwd: files\ngroup: files\nhosts: files\n")
        write(root, "etc/hosts", b"127.0.0.1 localhost\n")
        for name in ("libnss_files.so.2", "libnss_dns.so.2"):
            source = Path("/lib64") / name
            if source.is_file(): write(root, "lib64/" + name, source.read_bytes(), 0o755)
        for name, minor in (("null", 3), ("urandom", 9)):
            path = root / "dev" / name; path.parent.mkdir(exist_ok=True)
            os.mknod(path, stat.S_IFCHR | 0o666, os.makedev(1, minor))
        for name in ("om-oem-cgi", "om-api-v1"):
            write(root, "usr/libexec/openmitrastar/" + name, member(args.rootfs, "usr/libexec/openmitrastar/" + name), 0o755)
        for path in ("www/index.cgi", "www/dashboard.cgi", "www/logout.cgi", "www/api/v1/session", "www/api/v1/frontend"):
            write(root, path, member(args.rootfs, path), 0o755)
        for path in ("www/login.html", "www/login.css"):
            write(root, path, member(args.rootfs, path))
        refs = References(); refs.feed((root / "www/login.html").read_text())
        for url in refs.urls:
            if ".." in Path(url).parts or not url.startswith(("/assets/", "/branding/", "/font/")): continue
            write(root, "www" + url, member(args.rootfs, "www" + url))
        write(root, "run/openmitrastar/secrets/web.password.sha256", (digest(b"lab-only-password") + "\n").encode(), 0o600)
        write(root, "etc/openmitrastar/release", f"OPENMITRASTAR_PRODUCT_VERSION={args.base.upper()}-HTTP-HOST-TEST\n".encode())
        apply_overlay(root, args.package / "overlay", expected)
        _, transforms = apply_identity_transform(root, manifest)
        write(root, "www/__csrf_probe.cgi", b'#!/bin/sh\nprintf "Content-Type: text/plain\\r\\n\\r\\n%s\\n" "$HTTP_X_OM_CSRF"\n', 0o755)
        nonce = "lyoko-http-ready-" + os.urandom(8).hex()
        write(root, "www/" + nonce, nonce.encode())
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0)); port = reservation.getsockname()[1]
        config = f"data_dir=/www\nport={port}\nhost=127.0.0.1\ncgipat=**.cgi|cgi-bin/*|api/v1/*\npidfile=/run/mini_httpd.pid\ncharset=UTF-8\n"
        write(root, "etc/minihttpd.conf", config.encode())
        with (scratch / "server.log").open("wb") as log:
            process = subprocess.Popen([shutil.which("chroot"), str(root), "/bin/mini_httpd", "-D", "-u", "root", "-C", "/etc/minihttpd.conf"],
                                       stdout=log, stderr=log, start_new_session=True)
            try:
                ready = False
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        conn = HTTPConnection("127.0.0.1", port, timeout=.3); conn.request("GET", "/" + nonce)
                        response = conn.getresponse(); ready = response.status == 200 and response.read() == nonce.encode(); conn.close()
                        if ready: break
                    except OSError: pass
                    time.sleep(.05)
                if not ready: raise ValueError("native HTTP server did not start: " + (scratch / "server.log").read_text(errors="replace")[-1200:])
                tests = run_http_cases(port, root, manifest)
                if args.hold_seconds:
                    ready_file = args.report.with_suffix(".ready.json")
                    stop_file = args.report.with_suffix(".stop")
                    if ready_file.exists() or stop_file.exists(): raise ValueError("browser test control files already exist")
                    ready_file.write_text(json.dumps({"url": f"http://127.0.0.1:{port}/index.cgi", "native_server_pid": process.pid,
                                                     "synthetic_credentials": True, "hardware_actions": False}) + "\n", encoding="ascii")
                    try:
                        deadline = time.monotonic() + args.hold_seconds
                        while time.monotonic() < deadline and not stop_file.exists() and process.poll() is None:
                            time.sleep(.2)
                    finally:
                        ready_file.unlink(missing_ok=True); stop_file.unlink(missing_ok=True)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)
        report = {"schema": "lyoko.native-http-integration/v1", "status": "PASS", "base": args.base,
                  "rootfs_sha256": args.rootfs_sha256, "target_http_server_sha256": ARC_SERVER_SHA,
                  "server_sources": sources, "host_server_sha256": sha256(binary), "api_transforms": transforms,
                  "package_manifest_sha256": sha256(args.package / "manifest.json"), "tests": tests,
                  "network_scope": "ephemeral loopback port only", "hardware_actions": False,
                  "not_proven": ["ARC runtime", "HTTPS/TLS", "browser JavaScript execution", "radio hardware"], "release_eligible": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps({"status": "PASS", "base": args.base, "tests": len(tests), "report": str(args.report)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", choices=("f314", "f317"), default="f314")
    parser.add_argument("--package", type=Path); parser.add_argument("--report", type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--hold-seconds", type=int, default=0, help="Keep this isolated server briefly for browser validation (max 120)")
    parser.add_argument("--linux-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--rootfs", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--rootfs-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--server-source", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 <= args.hold_seconds <= 120: raise ValueError("hold-seconds must be 0..120")
    if args.linux_worker: linux_worker(args)
    else:
        import shlex
        from verify_lyoko_web_next_f314_rootfs import BASES, ROOT
        from package_lyoko_web_next import default_package_dir
        from build_f306_unified_product_from_f305 import run_wsl, wsl_path
        package = (args.package or default_package_dir()).resolve()
        report = (args.report or package / f"native-http-{args.base}.json").resolve()
        base = BASES[args.base]
        argv = ["python3", wsl_path(Path(__file__).resolve()), "--linux-worker", "--base", args.base,
                "--package", wsl_path(package), "--report", wsl_path(report), "--rootfs", wsl_path(base["rootfs"]), "--rootfs-sha256", base["sha256"],
                "--hold-seconds", str(args.hold_seconds),
                "--server-source", wsl_path(ROOT / "work/sources/Quantenna-GPL/buildroot/package/zminihttpd/mini_httpd-1.19")]
        print(run_wsl(shlex.join(argv), args.distro))


if __name__ == "__main__": main()
