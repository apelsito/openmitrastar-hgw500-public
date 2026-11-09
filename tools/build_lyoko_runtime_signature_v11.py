#!/usr/bin/env python3
"""Export verified raw Ed25519 assets for the two-package Lyoko v1.1 feed."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "outputs/packages/lyoko-v1.1/repository"
OUT = ROOT / "outputs/packages/lyoko-runtime-signature-v1.1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    packages = REPOSITORY / "Packages"
    signature_json = REPOSITORY / "Packages.sig.json"
    public_pem = REPOSITORY / "lyoko-feed-ed25519.pub"
    metadata = json.loads(signature_json.read_text(encoding="ascii"))
    message = packages.read_bytes()
    signature = base64.b64decode(metadata["signature"], validate=True)
    public_key = serialization.load_pem_public_key(public_pem.read_bytes())
    if not isinstance(public_key, Ed25519PublicKey):
        raise SystemExit("feed public key is not Ed25519")
    public_raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if len(signature) != 64 or len(public_raw) != 32:
        raise SystemExit("invalid raw Ed25519 asset size")
    if hashlib.sha256(message).hexdigest() != metadata["sha256"]:
        raise SystemExit("signature metadata does not match Packages")
    public_key.verify(signature, message)
    key_id = hashlib.sha256(public_raw).hexdigest()[:16]
    if metadata["key_id"] != key_id:
        raise SystemExit("feed key id mismatch")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "Packages.sig").write_bytes(signature)
    (OUT / "lyoko-feed-ed25519.raw").write_bytes(public_raw)
    (OUT / "Packages.sig.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="ascii")
    manifest = {
        "schema": "lyoko.feed-runtime-signature-assets/v2",
        "source": "outputs/packages/lyoko-v1.1",
        "packages_bytes": len(message),
        "packages_sha256": hashlib.sha256(message).hexdigest(),
        "key_id": key_id,
        "public_key_bytes": len(public_raw),
        "public_key_sha256": sha256(OUT / "lyoko-feed-ed25519.raw"),
        "signature_bytes": len(signature),
        "signature_sha256": sha256(OUT / "Packages.sig"),
        "verified_before_write": True,
        "private_key_present": False,
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
