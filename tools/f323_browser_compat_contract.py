"""Pure F323 bounds: two browser-compatibility fixes over exact installed F321."""
from __future__ import annotations

import hashlib
import re

from lyoko_config_store_status_contract import API_PATH, transform_bytes as api_bytes
from lyoko_web_rootfs_worker import validate_delta

SOURCE_CANDIDATE = "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18"
SOURCE_ROOTFS = "75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e"
SOURCE_MANIFEST = "2b8b2f2b2e2b845c1fe660b7f89feb34da113b60ad43c6c42f312f3621dc87ff"
SOURCE_RELEASE = "1959de970aecee799b8fe4fa67457d53d25e9e30868c323a307e77e452f81fa1"
API_AFTER = "f7e6568f9749a848f0f5f9b75cd7eec8b4d0346d2214cb987f0b173a6ad763e1"
RELEASE_PATH = "etc/openmitrastar/release"
PRODUCT_VERSION = "lyoko-foundation-6.9.2-f323-browser-compat-f321-device"
UI_VERSION = "0.3.1-classic-compat"
ROOTFS_OFFSET, ROOTFS_WINDOW, STORE_OFFSET, SLOT_BYTES = 0x180000, 0x460000, 0x5E0000, 0x7A0000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pinned(data: bytes, expected: str, label: str) -> None:
    if digest(data) != expected:
        raise ValueError("F323 source drift: " + label)


def release_bytes(source: bytes, build_id: str) -> bytes:
    pinned(source, SOURCE_RELEASE, "F321 release")
    if not re.fullmatch(r"[0-9a-f]{16}", build_id):
        raise ValueError("invalid F323 build identity")
    replacements = {
        "OPENMITRASTAR_PRODUCT_VERSION": PRODUCT_VERSION,
        "OPENMITRASTAR_UI_VERSION": UI_VERSION,
        "OPENMITRASTAR_BUILD_ID": build_id,
    }
    result, seen = [], set()
    for line in source.decode("ascii").splitlines(keepends=True):
        key = line.split("=", 1)[0]
        if key in replacements:
            if key in seen or not line.endswith("\n") or line.endswith("\r\n"):
                raise ValueError("duplicate or malformed release field")
            seen.add(key)
            line = key + "=" + replacements[key] + "\n"
        result.append(line)
    if seen != set(replacements):
        raise ValueError("missing F323 release field")
    return "".join(result).encode("ascii")


def verify_delta(before: dict, after: dict, expected: dict, ui_paths: set[str]) -> dict:
    if set(expected) != ui_paths | {API_PATH, RELEASE_PATH}:
        raise ValueError("F323 expected delta is outside UI/API/release")
    if expected[API_PATH]["sha256"] != API_AFTER or expected[API_PATH]["mode"] != "0755":
        raise ValueError("F323 API is not the exact status-only correction")
    return validate_delta(before, after, expected)


def verify_binary(source: bytes, source_rootfs: bytes, candidate: bytes, rootfs: bytes) -> None:
    pinned(source, SOURCE_CANDIDATE, "F321 candidate")
    pinned(source_rootfs, SOURCE_ROOTFS, "F321 rootfs")
    if source[ROOTFS_OFFSET:] != source_rootfs:
        raise ValueError("F321 rootfs sidecar mismatch")
    if (candidate[:4] != source[:4] or candidate[16:24] != source[16:24]
        or candidate[28:64] != source[28:64]):
        raise ValueError("F323 changed kernel load/entry or image type metadata")
    if candidate[64:ROOTFS_OFFSET] != source[64:ROOTFS_OFFSET]:
        raise ValueError("F323 changed header padding or kernel payload")
    if not rootfs.startswith(b"hsqs") or candidate[ROOTFS_OFFSET:] != rootfs:
        raise ValueError("F323 rootfs offset or sidecar mismatch")
    if not rootfs or len(rootfs) > ROOTFS_WINDOW or len(candidate) > STORE_OFFSET:
        raise ValueError("F323 exceeds the rootfs/store boundary")
