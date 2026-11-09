#!/usr/bin/env python3
"""Build a signed Lyoko package feed without retaining test private keys."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import lyoko_ipk


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "packages/lyoko")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/packages/lyoko-v1")
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--ephemeral-test-key", action="store_true")
    args = parser.parse_args()
    if bool(args.private_key) == bool(args.ephemeral_test_key):
        raise SystemExit("choose exactly one of --private-key or --ephemeral-test-key")

    output = args.output_dir.resolve()
    package_output = output / "packages"
    repository_output = output / "repository"
    package_output.mkdir(parents=True, exist_ok=True)
    built = []
    for recipe in sorted(args.source_dir.resolve().glob("*/package.json")):
        package = lyoko_ipk.build_package(recipe.parent, package_output)
        fields, _ = lyoko_ipk.read_control(package)
        built.append({
            "package": fields["Package"],
            "version": fields["Version"],
            "file": package.name,
            "bytes": package.stat().st_size,
            "sha256": lyoko_ipk.sha256_file(package),
        })
    if not built:
        raise SystemExit("no package recipes found")

    trust = "production"
    if args.ephemeral_test_key:
        trust = "ephemeral-test-only"
        with TemporaryDirectory(prefix="lyoko-feed-key-") as directory:
            key_path = Path(directory) / "feed.key"
            key = Ed25519PrivateKey.generate()
            key_path.write_bytes(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
            packages, signature = lyoko_ipk.build_index(package_output, repository_output, key_path)
    else:
        packages, signature = lyoko_ipk.build_index(package_output, repository_output, args.private_key.resolve())

    public = repository_output / "lyoko-feed-ed25519.pub"
    lyoko_ipk.verify_index(packages, signature, public, package_output)
    manifest = {
        "schema": "lyoko.package-feed/v1",
        "architecture": lyoko_ipk.ARCH,
        "kernel_abi": lyoko_ipk.KERNEL_ABI,
        "libc_abi": "uclibc",
        "platform": lyoko_ipk.PLATFORM,
        "trust": trust,
        "private_key_retained": False if args.ephemeral_test_key else "external",
        "packages": built,
        "index": {
            "file": "repository/Packages",
            "sha256": lyoko_ipk.sha256_file(packages),
            "gzip_file": "repository/Packages.gz",
            "gzip_sha256": lyoko_ipk.sha256_file(repository_output / "Packages.gz"),
            "signature_file": "repository/Packages.sig.json",
            "signature_raw_file": "repository/Packages.sig",
            "public_key_file": "repository/lyoko-feed-ed25519.pub",
            "public_key_raw_file": "repository/lyoko-feed-ed25519.raw",
        },
        "hardware_actions": {"router": False, "uart": False, "mtd": False},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
