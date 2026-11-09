#!/usr/bin/env python3
"""Verify a Lyoko feed and install selected IPKs into a SquashFS staging tree."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lyoko_ipk


def read_index(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8").strip()
    return [lyoko_ipk.parse_control(block.encode("utf-8")) for block in text.split("\n\n") if block.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--package", action="append", required=True)
    args = parser.parse_args()

    feed = args.feed_dir.resolve()
    packages_file = feed / "repository/Packages"
    signature = feed / "repository/Packages.sig.json"
    public_key = feed / "repository/lyoko-feed-ed25519.pub"
    public_key_raw = feed / "repository/lyoko-feed-ed25519.raw"
    signature_raw = feed / "repository/Packages.sig"
    package_dir = feed / "packages"
    lyoko_ipk.verify_index(packages_file, signature, public_key, package_dir)
    if not public_key_raw.is_file() or public_key_raw.stat().st_size != 32:
        raise SystemExit("missing raw Ed25519 feed public key")
    if not signature_raw.is_file() or signature_raw.stat().st_size != 64:
        raise SystemExit("missing raw Ed25519 feed signature")

    indexed = {row["Package"]: row for row in read_index(packages_file)}
    installed = []
    files = []
    for name in args.package:
        if name not in indexed:
            raise SystemExit(f"package not found in signed feed: {name}")
        row = indexed[name]
        package_path = package_dir / row["Filename"]
        paths = lyoko_ipk.install_tree(package_path, args.destination.resolve())
        installed.append({
            "package": name,
            "version": row["Version"],
            "architecture": row["Architecture"],
            "sha256": row["SHA256sum"],
        })
        files.extend(paths)

    metadata = args.destination.resolve() / "usr/share/lyoko/packages"
    metadata.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "lyoko.installed-packages/v1",
        "packages": installed,
        "files": sorted(files),
        "source_index_sha256": lyoko_ipk.sha256_file(packages_file),
        "signature_verified": True,
        "runtime_install": False,
    }
    (metadata / "installed.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
