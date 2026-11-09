#!/usr/bin/env python3
"""Patch one variable in a 64 KiB Quantenna Bootbase env and refresh CRC."""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import zlib


CRC_REGION_END = 0x6000


def patch_variable(blob: bytes, name: str, value: str) -> bytes:
    if len(blob) != 0x10000:
        raise ValueError(f"expected 65536 bytes, got {len(blob)}")
    stored = struct.unpack("<I", blob[:4])[0]
    calculated = zlib.crc32(blob[4:CRC_REGION_END]) & 0xFFFFFFFF
    if stored != calculated:
        raise ValueError(f"invalid input CRC: stored={stored:08x} calculated={calculated:08x}")

    data = bytearray(blob)
    end = data.find(b"\0\0", 4, 0x1000)
    if end < 0:
        raise ValueError("environment terminator not found")
    entries = bytes(data[4:end]).split(b"\0")
    key = name.encode("ascii") + b"="
    replacement = key + value.encode("ascii")
    found = False
    for index, entry in enumerate(entries):
        if entry.startswith(key):
            if len(entry) != len(replacement):
                raise ValueError("in-place patch requires equal-length value")
            entries[index] = replacement
            found = True
            break
    if not found:
        raise ValueError(f"variable not found: {name}")

    encoded = b"\0".join(entries) + b"\0\0"
    if len(encoded) != end - 4 + 2:
        raise AssertionError("environment length changed")
    data[4:4 + len(encoded)] = encoded
    crc = zlib.crc32(data[4:CRC_REGION_END]) & 0xFFFFFFFF
    data[:4] = struct.pack("<I", crc)
    return bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--value", required=True)
    args = parser.parse_args()
    result = patch_variable(args.source.read_bytes(), args.name, args.value)
    args.output.write_bytes(result)
    print(f"wrote={args.output} bytes={len(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
