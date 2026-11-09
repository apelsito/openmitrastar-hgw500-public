#!/usr/bin/env python3
"""Reproduce and fix HTTPS CGI routing with host-only loopback execution."""
from __future__ import annotations

import argparse
from http.client import HTTPSConnection
import json
from pathlib import Path
import shutil
import ssl
import tempfile

from build_minihttpd_wolfssl_trial import HOST_REPORT_SHA, QUALIFIED_SOURCE_SHA
from lyoko_https_profile import CONFIG_PATH, digest, modernize_config, routing_before_config
from lyoko_web_rootfs_worker import sha256
from verify_lyoko_http import member, run_http_cases
from verify_wolfssl_https import context, prepare_root, run, server

ARC_BINARY_SHA = "b105f5c80010b2cb09120e9c7b6dbee0cd2f4ea67be9834d66015f96b0102575"


def linux_worker(args):
    if sha256(args.rootfs) != args.rootfs_sha256: raise ValueError("pinned rootfs changed")
    host_path = args.host_trial / "manifest.json"
    if sha256(host_path) != HOST_REPORT_SHA: raise ValueError("host qualification changed")
    host = json.loads(host_path.read_text())
    binary = args.host_trial / "mini_httpd-wolfssl-host"
    if sha256(binary) != host["host_fixed_binary_sha256"]: raise ValueError("qualified host binary changed")
    arc = json.loads((args.arc_trial / "manifest.json").read_text())
    if (sha256(args.arc_trial / "mini_httpd-wolfssl") != ARC_BINARY_SHA
            or arc["binary_sha256"] != ARC_BINARY_SHA
            or arc["adapted_source_sha256"] != QUALIFIED_SOURCE_SHA
            or host["fixed_source_sha256"] != QUALIFIED_SOURCE_SHA):
        raise ValueError("ARC trial does not match the qualified source")
    if args.output.exists(): raise ValueError("refusing to overwrite HTTPS config evidence")
    manifest = json.loads((args.package / "manifest.json").read_text())
    if sha256(args.package / "manifest.json") != host["package_manifest_sha256"]:
        raise ValueError("qualified UI package changed")
    original = member(args.rootfs, CONFIG_PATH)
    fixed = modernize_config(original)
    with tempfile.TemporaryDirectory(prefix="lyoko-https-config-", dir="/tmp") as temporary:
        scratch = Path(temporary)
        cert, key = scratch / "test.crt", scratch / "test.key"
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
             "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost", "-keyout", str(key), "-out", str(cert)])
        root = prepare_root(args, scratch, manifest, cert, key)
        client = context(cert, ssl.TLSVersion.TLSv1_3)
        with server(root, binary, scratch / "before.log", True, client, routing_before_config()) as port:
            conn = HTTPSConnection("127.0.0.1", port, context=client, timeout=5)
            conn.request("GET", "/api/v1/session")
            response = conn.getresponse(); body = response.read(); status = response.status; conn.close()
            exposed_source = status == 200 and body == (root / "www/api/v1/session").read_bytes()
            if not exposed_source: raise ValueError("legacy CGI-route failure did not reproduce")
        results = {}
        with server(root, binary, scratch / "after.log", True, client, fixed) as port:
            for name, version in (("TLS1.2", ssl.TLSVersion.TLSv1_2), ("TLS1.3", ssl.TLSVersion.TLSv1_3)):
                results[name] = run_http_cases(port, root, manifest, tls_context=context(cert, version))
        report = {
            "schema": "lyoko.https-config-qualification/v1", "status": "PASS", "base": args.base,
            "rootfs_sha256": args.rootfs_sha256, "config_path": CONFIG_PATH,
            "original_config_sha256": digest(original), "fixed_config_sha256": digest(fixed),
            "before_profile": "legacy CGI routing only; compatible new TLS cipher syntax in both cases",
            "reproduced_source_disclosure": exposed_source, "source_content_recorded": False,
            "host_qualification_sha256": HOST_REPORT_SHA, "server_source_sha256": QUALIFIED_SOURCE_SHA,
            "arc_binary_sha256": ARC_BINARY_SHA, "package_manifest_sha256": host["package_manifest_sha256"],
            "test_substitutions": ["loopback address", "ephemeral port", "temporary certificate path", "temporary pid path"],
            "tests": results, "network_scope": "host ephemeral loopback only",
            "hardware_actions": False, "private_key_saved": False, "release_eligible": False,
            "not_proven": ["ARC runtime", "device TLS peak RAM", "radio regression", "boot-time certificate/entropy readiness"],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".https-config-", dir=args.output.parent) as staging:
            stage = Path(staging) / "payload"; stage.mkdir()
            (stage / "minihttpd-https.conf").write_bytes(fixed)
            (stage / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
            stage.rename(args.output)
    print(json.dumps({"status": "PASS", "base": args.base, "routing_failure_reproduced_and_fixed": True,
                      "tests": {name: len(rows) for name, rows in results.items()}, "output": str(args.output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", choices=("f314", "f317"), default="f314")
    parser.add_argument("--output", type=Path); parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--linux-worker", action="store_true", help=argparse.SUPPRESS)
    for name in ("rootfs", "package", "host-trial", "arc-trial"):
        parser.add_argument("--" + name, type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--rootfs-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.linux_worker: linux_worker(args)
    else:
        import shlex
        from verify_lyoko_web_next_f314_rootfs import ROOT, BASES
        from package_lyoko_web_next import default_package_dir
        from build_f306_unified_product_from_f305 import run_wsl, wsl_path
        output = (args.output or ROOT / f"outputs/userland/https-config-{args.base}-qualification").resolve()
        command = ["python3", wsl_path(Path(__file__).resolve()), "--linux-worker", "--base", args.base,
                   "--output", wsl_path(output), "--rootfs", wsl_path(BASES[args.base]["rootfs"]),
                   "--rootfs-sha256", BASES[args.base]["sha256"], "--package", wsl_path(default_package_dir()),
                   "--host-trial", wsl_path(ROOT / "outputs/userland/wolfssl-https-host-qualification"),
                   "--arc-trial", wsl_path(ROOT / "outputs/userland/minihttpd-wolfssl-5.9.2-arc700-cgi-tls-trial")]
        print(run_wsl(shlex.join(command), args.distro, timeout=300))


if __name__ == "__main__": main()
