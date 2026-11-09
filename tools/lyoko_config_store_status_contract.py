"""Pure, hash-pinned fix for the installed F321 config/store status guard.

This module does not read or write files, build firmware, contact a device, or
enable persistence.  Integrating its result into any future artifact remains a
separate, versioned and authorized operation.
"""

from __future__ import annotations

import hashlib


API_PATH = "usr/libexec/openmitrastar/om-api-v1"
TRANSFORM_ID = "f321-config-store-status-literal-brace/v1"
SOURCE_SHA256 = "849ffe6a503d3be2a3083116dcafb6a6c4adf32f7eeee4a727bf64391caa1b09"
OLD_GUARD = b"grep -q '^\\{\"schema\":\"openmitrastar.config-store/v1\"'"
NEW_GUARD = b"grep -q '^[{]\"schema\":\"openmitrastar.config-store/v1\"'"


def transform_bytes(source: bytes) -> bytes:
    """Replace only F321's non-portable BRE brace; reject any other input."""
    if not isinstance(source, bytes):
        raise TypeError("F321 API input must be bytes")
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("API input is not the exact pinned F321 source")

    start = source.index(b"\nconfig/store)\n")
    end = source.index(b"\ndiagnostics)\n", start)
    branch = source[start:end]
    if source.count(OLD_GUARD) != 1 or branch.count(OLD_GUARD) != 1:
        raise ValueError("F321 config/store guard is not unique in its branch")
    if NEW_GUARD in source:
        raise ValueError("F321 config/store guard is already transformed")

    return source[:start] + branch.replace(OLD_GUARD, NEW_GUARD, 1) + source[end:]
