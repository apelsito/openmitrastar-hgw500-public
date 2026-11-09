#!/usr/bin/env python3
"""Derive public raw Ed25519 runtime assets from an already signed feed."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, default=ROOT / "outputs/packages/lyoko-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/packages/lyoko-runtime-signature")
    args = parser.parse_args()

    repository = args.feed.resolve() / "repository"
    packages = (repository / "Packages").read_bytes()
    metadata = json.loads((repository / "Packages.sig.json").read_text(encoding="ascii"))
    public = serialization.load_pem_public_key((repository / "lyoko-feed-ed25519.pub").read_bytes())
    if not isinstance(public, Ed25519PublicKey):
        raise SystemExit("feed public key is not Ed25519")
    if metadata.get("schema") != "lyoko.package-feed-signature/v1" or metadata.get("algorithm") != "ed25519":
        raise SystemExit("unsupported feed signature metadata")
    if metadata.get("sha256") != hashlib.sha256(packages).hexdigest():
        raise SystemExit("feed index digest mismatch")
    signature = base64.b64decode(metadata.get("signature", ""), validate=True)
    if len(signature) != 64:
        raise SystemExit("invalid Ed25519 signature size")
    public_raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if metadata.get("key_id") != hashlib.sha256(public_raw).hexdigest()[:16]:
        raise SystemExit("feed key id mismatch")
    public.verify(signature, packages)

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "lyoko-feed-ed25519.raw").write_bytes(public_raw)
    (output / "Packages.sig").write_bytes(signature)
    manifest = {
        "schema": "lyoko.feed-runtime-signature-assets/v1",
        "source": str(args.feed.resolve()),
        "packages_sha256": hashlib.sha256(packages).hexdigest(),
        "public_key_bytes": len(public_raw),
        "public_key_sha256": hashlib.sha256(public_raw).hexdigest(),
        "key_id": metadata["key_id"],
        "signature_bytes": len(signature),
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
        "verified_before_write": True,
        "private_key_present": False,
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
