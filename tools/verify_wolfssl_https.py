#!/usr/bin/env python3
"""Native-host TLS qualification, explicitly distinct from ARC execution."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPSConnection
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import stat
import subprocess
import tarfile
import tempfile
import time
from urllib.parse import urlencode

from build_wolfssl_arc700_trial import OPTIONS, SOURCE_COMMIT, SOURCE_SHA, CMAKE_SHA, patch_options_template, patch_cmake_profile
from build_minihttpd_wolfssl_trial import patch_tls_environment
from verify_lyoko_http import digest, member, write, References, run_http_cases
from lyoko_https_profile import CIPHERS, loopback_config


def run(argv, cwd=None, timeout=600):
    process = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if process.returncode: raise RuntimeError("TLS qualification command failed:\n" + (process.stdout + process.stderr)[-6500:])
    return process.stdout


def build_host(args, scratch):
    if digest(args.archive.read_bytes()) != SOURCE_SHA or digest(args.cmake.read_bytes()) != CMAKE_SHA: raise ValueError("build input drift")
    with tarfile.open(args.archive) as archive: archive.extractall(scratch, filter="data")
    source = scratch / ("wolfssl-" + SOURCE_COMMIT)
    template = source / "cmake/options.h.in"; template.write_bytes(patch_options_template(template.read_bytes()))
    cmake_list = source / "CMakeLists.txt"; cmake_list.write_bytes(patch_cmake_profile(cmake_list.read_bytes()))
    prefix = scratch / "wolf-install"; build = scratch / "wolf-build"
    run([str(args.cmake), "-S", str(source), "-B", str(build), "-G", "Unix Makefiles", "-DCMAKE_BUILD_TYPE=MinSizeRel",
         f"-DCMAKE_INSTALL_PREFIX={prefix}", "-DCMAKE_C_FLAGS=-Os -ffunction-sections -fdata-sections", *[f"-D{key}={value}" for key, value in OPTIONS.items()]])
    run([str(args.cmake), "--build", str(build), "--parallel", "2"])
    run([str(args.cmake), "--install", str(build)])
    libraries = list(prefix.rglob("libwolfssl.a"))
    if len(libraries) != 1: raise ValueError("host wolfSSL archive missing")
    return prefix, libraries[0]


def compile_server(args, scratch, prefix, library, source, name):
    build = scratch / name; build.mkdir()
    for item in ("match.c", "tdate_parse.c", "version.h", "port.h", "match.h", "tdate_parse.h", "mime_encodings.txt", "mime_types.txt", "Makefile"):
        shutil.copyfile(args.server_source / item, build / item)
    (build / "mini_httpd.c").write_bytes(source)
    run(["make", "-s", "mime_encodings.h", "mime_types.h"], cwd=build)
    output = build / name
    run(["gcc", "-std=gnu99", "-Os", "-DUSE_SSL", "-DNO_IPV6", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
         "-I" + str(prefix / "include"), "-o", str(output), str(build / "mini_httpd.c"), str(build / "match.c"), str(build / "tdate_parse.c"), str(library), "-lcrypt", "-lm"])
    return output


def prepare_root(args, scratch, manifest, cert, key):
    from verify_lyoko_cgi_sessions import copy_host_tool
    from lyoko_web_rootfs_worker import apply_overlay, apply_identity_transform, validate_overlay
    root = scratch / "root"; root.mkdir()
    for tool in ("sh", "cat", "sed", "head", "cut", "sha256sum", "rm", "awk", "date", "id", "ls", "mkdir", "chmod", "mv", "dd", "sleep", "tr", "wc"):
        copy_host_tool(root, tool)
    (root / "bin/ash").symlink_to("sh")
    write(root, "etc/passwd", b"root:x:0:0:root:/root:/bin/sh\n")
    write(root, "etc/group", b"root:x:0:\n")
    write(root, "etc/nsswitch.conf", b"passwd: files\ngroup: files\nhosts: files\n")
    write(root, "etc/hosts", b"127.0.0.1 localhost\n")
    for name in ("libnss_files.so.2", "libnss_dns.so.2"):
        library = Path("/lib64") / name
        if library.is_file(): write(root, "lib64/" + name, library.read_bytes(), 0o755)
    for name, minor in (("null", 3), ("urandom", 9)):
        path = root / "dev" / name; path.parent.mkdir(exist_ok=True)
        os.mknod(path, stat.S_IFCHR | 0o666, os.makedev(1, minor))
    for path in ("usr/libexec/openmitrastar/om-oem-cgi", "usr/libexec/openmitrastar/om-api-v1", "www/index.cgi", "www/dashboard.cgi", "www/logout.cgi", "www/api/v1/session", "www/api/v1/frontend"):
        write(root, path, member(args.rootfs, path), 0o755)
    for path in ("www/login.html", "www/login.css"): write(root, path, member(args.rootfs, path))
    refs = References(); refs.feed((root / "www/login.html").read_text())
    for url in refs.urls:
        if ".." not in Path(url).parts and url.startswith(("/assets/", "/branding/", "/font/")): write(root, "www" + url, member(args.rootfs, "www" + url))
    write(root, "run/openmitrastar/secrets/web.password.sha256", (digest(b"lab-only-password") + "\n").encode(), 0o600)
    write(root, "run/https.pem", cert.read_bytes() + key.read_bytes(), 0o600)
    write(root, "etc/openmitrastar/release", b"OPENMITRASTAR_PRODUCT_VERSION=HTTPS-HOST-TEST\n")
    apply_overlay(root, args.package / "overlay", validate_overlay(args.package / "overlay", manifest))
    apply_identity_transform(root, manifest)
    write(root, "www/__csrf_probe.cgi", b'#!/bin/sh\nprintf "Content-Type: text/plain\\r\\n\\r\\n%s\\n" "$HTTP_X_OM_CSRF"\n', 0o755)
    write(root, "www/__transport.cgi", b'#!/bin/sh\nprintf "Content-Type: text/plain\\r\\n\\r\\n%s\\n" "${HTTPS:-unset}"\n', 0o755)
    return root


def context(cert, version):
    result = ssl.create_default_context(cafile=str(cert))
    result.minimum_version = version; result.maximum_version = version
    return result


@contextmanager
def server(root, binary, log_path, tls, client_context, config_profile=None):
    from verify_lyoko_cgi_sessions import copy_host_tool
    copy_host_tool(root, binary.name, binary)
    with socket.socket() as reservation: reservation.bind(("127.0.0.1", 0)); port = reservation.getsockname()[1]
    config = f"data_dir=/www\nport={port}\nhost=127.0.0.1\ncgipat=**.cgi|api/v1/*\npidfile=/run/mini_httpd.pid\ncharset=UTF-8\n"
    if tls: config += "ssl\ncertfile=/run/https.pem\ncipher=" + CIPHERS + "\n"
    if config_profile is not None and not tls: raise ValueError("HTTPS profile requires TLS")
    write(root, "etc/minihttpd.conf", loopback_config(config_profile, port) if config_profile is not None else config.encode())
    with log_path.open("wb") as log:
        process = subprocess.Popen([shutil.which("chroot"), str(root), "/bin/" + binary.name, "-D", "-u", "root", "-C", "/etc/minihttpd.conf"], stdout=log, stderr=log, start_new_session=True)
        try:
            ready = False
            deadline = time.monotonic() + 8
            last_error = ""
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    connection = HTTPSConnection("127.0.0.1", port, timeout=1, context=client_context) if tls else HTTPConnection("127.0.0.1", port, timeout=1)
                    connection.request("GET", "/__transport.cgi")
                    response = connection.getresponse(); response.read(); ready = response.status == 200; connection.close()
                    if ready: break
                except (OSError, ssl.SSLError) as error: last_error = str(error)
                time.sleep(.1)
            if not ready: raise ValueError(f"server did not become ready: {last_error}\n{log_path.read_text(errors='replace')[-2000:]}")
            yield port
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)


def transport(port, tls_context=None, headers=None):
    conn = HTTPSConnection("127.0.0.1", port, timeout=3, context=tls_context) if tls_context else HTTPConnection("127.0.0.1", port, timeout=3)
    conn.request("GET", "/__transport.cgi", headers=headers or {})
    response = conn.getresponse(); body = response.read().decode().strip(); conn.close()
    return body


def login_cookie(port, tls_context):
    conn = HTTPSConnection("127.0.0.1", port, timeout=3, context=tls_context)
    conn.request("POST", "/index.cgi", body=urlencode({"login_password": "lab-only-password"}), headers={"Content-Type": "application/x-www-form-urlencoded"})
    response = conn.getresponse(); cookie = response.getheader("Set-Cookie", ""); response.read(); conn.close()
    if response.status != 302: raise ValueError("test login failed")
    return cookie


def linux_worker(args):
    from lyoko_web_rootfs_worker import sha256
    if sha256(args.rootfs) != args.rootfs_sha256: raise ValueError("rootfs changed")
    if args.output.exists(): raise ValueError("refusing to overwrite TLS qualification")
    manifest = json.loads((args.package / "manifest.json").read_text())
    arc = json.loads((args.arc_trial / "manifest.json").read_text())
    before_source = (args.arc_trial / "mini_httpd-adapted.c").read_bytes()
    if digest(before_source) != arc["adapted_source_sha256"]: raise ValueError("ARC trial source changed")
    after_source = patch_tls_environment(before_source)
    def checkpoint(stage, status="RUNNING", **details):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        path = args.output.with_suffix(".progress.json")
        path.write_text(json.dumps({"stage": stage, "status": status, "hardware_actions": False, **details}, indent=2) + "\n", encoding="ascii")
    checkpoint("building-host-profile")
    with tempfile.TemporaryDirectory(prefix="lyoko-https-", dir="/tmp") as directory:
        scratch = Path(directory)
        prefix, library = build_host(args, scratch)
        before_binary = compile_server(args, scratch, prefix, library, before_source, "mini-before")
        after_binary = compile_server(args, scratch, prefix, library, after_source, "mini-fixed")
        cert = scratch / "test.crt"; key = scratch / "test.key"
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
             "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost", "-keyout", str(key), "-out", str(cert)])
        root = prepare_root(args, scratch, manifest, cert, key)
        checkpoint("host-profile-built")
        tls13 = context(cert, ssl.TLSVersion.TLSv1_3)
        with server(root, before_binary, scratch / "before.log", True, tls13) as port:
            baseline_env = transport(port, tls13)
            baseline_secure = "Secure" in login_cookie(port, tls13)
            if baseline_env != "unset" or baseline_secure: raise ValueError("CGI TLS-context finding was not reproduced as expected")
            checkpoint("missing-secure-cookie-reproduced", https_cgi_value=baseline_env, session_cookie_secure=baseline_secure)
        results = {}
        negotiations = {}
        with server(root, after_binary, scratch / "after.log", True, tls13) as port:
            if transport(port, tls13, {"X-Forwarded-Proto": "http", "HTTPS": "off"}) != "on": raise ValueError("TLS context can be downgraded by headers")
            for name, version in (("TLS1.2", ssl.TLSVersion.TLSv1_2), ("TLS1.3", ssl.TLSVersion.TLSv1_3)):
                client = context(cert, version)
                conn = HTTPSConnection("127.0.0.1", port, context=client, timeout=3); conn.connect()
                negotiations[name] = {"version": conn.sock.version(), "cipher": conn.sock.cipher()}; conn.close()
                results[name] = run_http_cases(port, root, manifest, tls_context=client)
                checkpoint("https-profile-passed", protocol=name, tests=len(results[name]), negotiation=negotiations[name])
            rejected = {}
            for name, version in (("TLS1.0", ssl.TLSVersion.TLSv1), ("TLS1.1", ssl.TLSVersion.TLSv1_1)):
                client = context(cert, version); client.set_ciphers("ALL:@SECLEVEL=0")
                conn = HTTPSConnection("127.0.0.1", port, context=client, timeout=3)
                try: conn.connect(); raise ValueError(f"obsolete protocol accepted: {name}")
                except ssl.SSLError as error:
                    if error.reason != "TLSV1_ALERT_PROTOCOL_VERSION": raise ValueError(f"cannot attribute rejection to server protocol policy: {error}")
                    rejected[name] = error.reason
                finally: conn.close()
            untrusted = HTTPSConnection("127.0.0.1", port, context=ssl.create_default_context(), timeout=3)
            try: untrusted.connect(); raise ValueError("untrusted test certificate unexpectedly accepted")
            except ssl.SSLCertVerificationError: pass
            finally: untrusted.close()
        with server(root, after_binary, scratch / "plain.log", False, None) as port:
            if transport(port, headers={"HTTPS": "on", "X-Forwarded-Proto": "https", "X-Forwarded-SSL": "on"}) != "unset":
                raise ValueError("plaintext request can spoof HTTPS CGI state")
        report = {"schema": "lyoko.wolfssl-https-host-qualification/v1", "status": "PASS", "wolfssl_version": "5.9.2",
                  "requested_options": OPTIONS, "source_commit": SOURCE_COMMIT, "source_archive_sha256": SOURCE_SHA,
                  "before_source_sha256": digest(before_source), "fixed_source_sha256": digest(after_source),
                  "host_fixed_binary_sha256": sha256(after_binary), "package_manifest_sha256": sha256(args.package / "manifest.json"),
                  "reproduced_before_fix": {"https_cgi_value": baseline_env, "session_cookie_secure": baseline_secure},
                  "fixed_boundary": {"https_sets_server_owned_flag": True, "https_cookie_secure": True, "http_header_spoof_rejected": True},
                  "negotiations": negotiations, "obsolete_protocols_rejected": rejected, "untrusted_certificate_rejected": True,
                  "tls_http_tests": results, "test_certificate_sha256": sha256(cert), "private_key_saved": False,
                  "not_proven": ["ARC runtime handshake", "peak device RAM", "physical radio regression"], "hardware_actions": False, "release_eligible": False}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".https-qualified-", dir=args.output.parent) as temporary:
            stage = Path(temporary) / "payload"; stage.mkdir()
            shutil.copy2(after_binary, stage / "mini_httpd-wolfssl-host")
            (stage / "mini_httpd-fixed.c").write_bytes(after_source)
            (stage / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
            stage.rename(args.output)
    checkpoint("complete", status="PASS", report_sha256=sha256(args.output / "manifest.json"))
    print(json.dumps({"status": "PASS", "output": str(args.output), "negotiations": negotiations,
                      "tests": {name: len(rows) for name, rows in results.items()}, "transport_boundary_fixed": True}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path); parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--linux-worker", action="store_true", help=argparse.SUPPRESS)
    for name in ("archive", "cmake", "server-source", "arc-trial", "rootfs", "package"): parser.add_argument("--" + name, type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--rootfs-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.linux_worker: linux_worker(args)
    else:
        import shlex
        from verify_lyoko_web_next_f314_rootfs import ROOT, BASES
        from package_lyoko_web_next import default_package_dir
        from build_f306_unified_product_from_f305 import run_wsl, wsl_path
        output = (args.output or ROOT / "outputs/userland/wolfssl-https-host-qualification").resolve()
        command = ["python3", wsl_path(Path(__file__).resolve()), "--linux-worker", "--output", wsl_path(output),
                   "--archive", wsl_path(ROOT / "work/sources/wolfssl-5.9.2-ac01707f.tar.gz"),
                   "--cmake", wsl_path(ROOT / "tools/external/cmake-4.4.3-linux/cmake/data/bin/cmake"),
                   "--server-source", wsl_path(ROOT / "work/sources/Quantenna-GPL/buildroot/package/zminihttpd/mini_httpd-1.19"),
                   "--arc-trial", wsl_path(ROOT / "outputs/userland/minihttpd-wolfssl-5.9.2-arc700-trial"),
                   "--package", wsl_path(default_package_dir()), "--rootfs", wsl_path(BASES["f314"]["rootfs"]),
                   "--rootfs-sha256", BASES["f314"]["sha256"]]
        print(run_wsl(shlex.join(command), args.distro, timeout=900))


if __name__ == "__main__": main()
