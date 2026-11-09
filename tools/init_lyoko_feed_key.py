#!/usr/bin/env python3
"""Create the local Lyoko package-feed signing key without exposing it."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-key",
        type=Path,
        default=Path.home() / ".openmitrastar/keys/lyoko-feed-ed25519.pem",
    )
    args = parser.parse_args()
    path = args.private_key.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise SystemExit("existing key is not Ed25519")
        created = False
    else:
        key = Ed25519PrivateKey.generate()
        path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        os.chmod(path, 0o600)
        created = True
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print(f"LYOKO_FEED_KEY_READY created={int(created)} key_id={hashlib.sha256(public).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
