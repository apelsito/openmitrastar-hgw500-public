#!/usr/bin/env python3
"""Host-verified remote package operations for a physical Lyoko appliance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import integrate_lyoko_packages as integration
import lyoko_ipk


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "outputs/packages/lyoko-v1.1"
DEFAULT_KEY = Path.home() / ".ssh/id_ed25519"
PINNED_KEY_ID = "01ed300cc2b2a01d"
INSTALL_ACK = "OPENMITRASTAR_LYOKO_PKG_VOLATILE_INSTALL"
REMOVE_ACK = "OPENMITRASTAR_LYOKO_PKG_VOLATILE_REMOVE"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+_.-]*$")


def key_id(public_key: Path) -> str:
    public = serialization.load_pem_public_key(public_key.read_bytes())
    if not isinstance(public, Ed25519PublicKey):
        raise ValueError("feed public key is not Ed25519")
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def verified_feed(feed: Path) -> dict[str, dict[str, str]]:
    packages = feed / "repository/Packages"
    signature = feed / "repository/Packages.sig.json"
    public_key = feed / "repository/lyoko-feed-ed25519.pub"
    package_dir = feed / "packages"
    if key_id(public_key) != PINNED_KEY_ID:
        raise ValueError("feed signing key is not the pinned Lyoko key")
    lyoko_ipk.verify_index(packages, signature, public_key, package_dir)
    return {row["Package"]: row for row in integration.read_index(packages)}


def ssh_base(host: str, key: Path) -> list[str]:
    return [
        str(Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"),
        "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
        "-o", "LogLevel=ERROR", f"root@{host}",
    ]


def remote(host: str, key: Path, command: str, *, data: bytes | None = None, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*ssh_base(host, key), command],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def plan(action: str, name: str, feed: Path) -> dict[str, object]:
    indexed = verified_feed(feed)
    if action in {"install", "verify"} and name not in indexed:
        raise ValueError(f"package not found: {name}")
    row = indexed.get(name, {})
    return {
        "schema": "openmitrastar.lyoko-pkg-remote-plan/v1",
        "action": action,
        "package": name,
        "version": row.get("Version"),
        "architecture": row.get("Architecture"),
        "sha256": row.get("SHA256sum"),
        "host_verification": "ed25519+pinned-key+sha256+abi",
        "remote_stage": "/run/lyoko-feed-upload",
        "install_root": "/run/lyoko-packages",
        "persistent_write": False,
        "flash": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "list", "verify", "install", "remove"))
    parser.add_argument("package", nargs="?", default="")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.package and not NAME_RE.fullmatch(args.package):
        raise SystemExit("invalid package name")
    if args.action in {"verify", "install", "remove"} and not args.package:
        raise SystemExit("package name is required")

    feed = args.feed.resolve()
    operation = plan(args.action, args.package, feed)
    print(json.dumps(operation, indent=2))
    if not args.execute:
        return 0
    if args.action == "install" and args.ack != INSTALL_ACK:
        raise SystemExit("exact volatile-install acknowledgement required")
    if args.action == "remove" and args.ack != REMOVE_ACK:
        raise SystemExit("exact volatile-remove acknowledgement required")

    preflight = remote(
        args.host, args.key,
        "test -x /usr/bin/lyoko-pkg && test -x /usr/libexec/lyoko/pkgbox && /usr/bin/lyoko-pkg status",
    )
    if preflight.returncode:
        raise SystemExit(preflight.stderr.decode("utf-8", "replace") or "lyoko-pkg unavailable")

    if args.action in {"status", "list"}:
        result = remote(args.host, args.key, f"/usr/bin/lyoko-pkg {args.action}")
    elif args.action == "remove":
        result = remote(args.host, args.key, f"/usr/bin/lyoko-pkg remove {args.package}")
    else:
        indexed = verified_feed(feed)
        row = indexed[args.package]
        package = feed / "packages" / row["Filename"]
        stage = f"/run/lyoko-feed-upload/{args.package}-{row['SHA256sum'][:8]}"
        create = remote(args.host, args.key, f"rm -rf {stage}; mkdir -p {stage}/archives")
        if create.returncode:
            raise SystemExit(create.stderr.decode("utf-8", "replace"))
        uploads = (
            (feed / "repository/Packages", f"{stage}/Packages"),
            (feed / "repository/Packages.sig.json", f"{stage}/Packages.sig.json"),
            (feed / "repository/lyoko-feed-ed25519.pub", f"{stage}/lyoko-feed-ed25519.pub"),
            (package, f"{stage}/archives/{package.name}"),
        )
        for source, target in uploads:
            uploaded = remote(args.host, args.key, f"umask 077; cat > {target}", data=source.read_bytes())
            if uploaded.returncode:
                raise SystemExit(f"upload failed: {source.name}")
        verify = remote(
            args.host, args.key,
            f"test \"$(sha256sum {stage}/archives/{package.name} | cut -d' ' -f1)\" = {row['SHA256sum']}",
        )
        if verify.returncode:
            raise SystemExit("remote package SHA-256 mismatch")
        command = (
            f"LYOKO_FEED_ROOT={stage} LYOKO_PKG_RUN_ROOT=/run/lyoko-packages "
            f"/usr/bin/lyoko-pkg {args.action} {args.package}; rc=$?; rm -rf {stage}; exit $rc"
        )
        result = remote(args.host, args.key, command, timeout=180)

    stdout = result.stdout.decode("utf-8", "replace")
    stderr = result.stderr.decode("utf-8", "replace")
    evidence = {
        **operation,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "stdout": stdout,
        "stderr": stderr,
        "returncode": result.returncode,
    }
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "result.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(stdout, end="")
    if result.returncode:
        print(stderr, end="", file=__import__("sys").stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
