#!/usr/bin/env python3
"""Copy an ELF32 little-endian ARC binary while changing only OSABI e_flags."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct


EF_ARC_OSABI_MSK = 0x00000F00
EF_ARC_OSABI_V4 = 0x00000400
EM_ARC_COMPACT = 93


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    raw = bytearray(args.source.read_bytes())
    if len(raw) < 52 or raw[:4] != b"\x7fELF" or raw[4] != 1 or raw[5] != 1:
        raise SystemExit("require ELF32 little-endian input")
    machine = struct.unpack_from("<H", raw, 18)[0]
    if machine != EM_ARC_COMPACT:
        raise SystemExit(f"require EM_ARC_COMPACT={EM_ARC_COMPACT}, got {machine}")
    old_flags = struct.unpack_from("<I", raw, 36)[0]
    new_flags = (old_flags & ~EF_ARC_OSABI_MSK) | EF_ARC_OSABI_V4
    struct.pack_into("<I", raw, 36, new_flags)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_bytes(raw)
    print(
        f"ARC_ELF_OSABI_PATCH_PASS old_flags={old_flags:#x} new_flags={new_flags:#x} "
        f"bytes={len(raw)} source_sha256={sha256(args.source.read_bytes())} "
        f"destination_sha256={sha256(raw)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
