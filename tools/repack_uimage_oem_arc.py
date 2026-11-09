#!/usr/bin/env python3
"""Rewrite only the legacy uImage architecture byte for old MitraStar Bootbase.

Modern mkimage assigns ARC architecture id 0x17. The 2015 Bootbase build in
this device predates enum additions and its known-good images use 0x13. This
tool keeps the payload, data CRC, load address and entry point unchanged, then
recomputes the 64-byte header CRC.
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

UIMAGE_MAGIC = 0x27051956
HEADER_SIZE = 64
ARCH_OFFSET = 29
HCRC_OFFSET = 4
OEM_ARC_ARCH = 0x13


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    image = bytearray(args.source.read_bytes())
    if len(image) < HEADER_SIZE:
        raise SystemExit("input is shorter than a legacy uImage header")
    magic, _, _, size, load, entry, data_crc = struct.unpack(">7I", image[:28])
    if magic != UIMAGE_MAGIC:
        raise SystemExit(f"bad uImage magic: 0x{magic:08x}")
    if len(image) != HEADER_SIZE + size:
        raise SystemExit(f"size mismatch: header={size}, file={len(image) - HEADER_SIZE}")
    actual_data_crc = zlib.crc32(image[HEADER_SIZE:]) & 0xFFFFFFFF
    if actual_data_crc != data_crc:
        raise SystemExit(
            f"bad payload CRC: header=0x{data_crc:08x}, actual=0x{actual_data_crc:08x}"
        )

    old_arch = image[ARCH_OFFSET]
    image[ARCH_OFFSET] = OEM_ARC_ARCH
    image[HCRC_OFFSET:HCRC_OFFSET + 4] = b"\0\0\0\0"
    header_crc = zlib.crc32(image[:HEADER_SIZE]) & 0xFFFFFFFF
    image[HCRC_OFFSET:HCRC_OFFSET + 4] = struct.pack(">I", header_crc)

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_bytes(image)
    print(
        f"wrote {args.destination} ({len(image)} bytes): "
        f"arch 0x{old_arch:02x}->0x{OEM_ARC_ARCH:02x}, "
        f"load=0x{load:08x}, entry=0x{entry:08x}, hcrc=0x{header_crc:08x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
