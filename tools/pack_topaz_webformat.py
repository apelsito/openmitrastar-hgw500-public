#!/usr/bin/env python3
"""Wrap a standard uImage in the HGW-500BNA-QCv2 0x2000 RAS layout."""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


MAGIC = 0x27051956
UIMAGE_HEADER = 64
RAS_PAYLOAD_OFFSET = 0x2000
OEM_ARC_ARCH = 0x13


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("uimage", type=Path)
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.uimage.read_bytes()
    template = args.template.read_bytes()
    if len(source) < UIMAGE_HEADER or len(template) < RAS_PAYLOAD_OFFSET:
        raise ValueError("source or template is too short")
    values = list(struct.unpack(">7I4B32s", source[:UIMAGE_HEADER]))
    if values[0] != MAGIC:
        raise ValueError("source is not a legacy uImage")
    source_size = values[3]
    if len(source) != UIMAGE_HEADER + source_size:
        raise ValueError("source uImage size does not match ih_size")
    payload = source[UIMAGE_HEADER:]
    if zlib.crc32(payload) & 0xFFFFFFFF != values[6]:
        raise ValueError("source uImage payload CRC is invalid")

    # Keep the model/provider RAS metadata at 0x40..0x1fff.  Bootbase's
    # chkimage hashes the actual kernel payload from 0x2000, not from 0x40.
    image = bytearray(template[:RAS_PAYLOAD_OFFSET])
    image.extend(payload)
    values[1] = 0
    values[3] = len(payload)
    values[6] = zlib.crc32(payload) & 0xFFFFFFFF
    values[8] = OEM_ARC_ARCH
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    image[:UIMAGE_HEADER] = struct.pack(">7I4B32s", *values)

    verify = bytearray(image[:UIMAGE_HEADER])
    verify[4:8] = b"\0\0\0\0"
    if zlib.crc32(verify) & 0xFFFFFFFF != values[1]:
        raise AssertionError("header CRC verification failed")
    if zlib.crc32(image[RAS_PAYLOAD_OFFSET:]) & 0xFFFFFFFF != values[6]:
        raise AssertionError("RAS payload CRC verification failed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    print(
        f"wrote {args.output} size={len(image)} payload={len(payload)} "
        f"hcrc=0x{values[1]:08x} dcrc=0x{values[6]:08x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
