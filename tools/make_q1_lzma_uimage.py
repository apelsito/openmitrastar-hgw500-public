#!/usr/bin/env python3
"""Build a deterministic OEM-ARC legacy uImage from an LZMA-alone payload.

The input uImage is the already verified, uncompressed Q1 kernel+initramfs.
Only its payload encoding changes: the decompressed byte stream, load address,
entry point, timestamp, OS and image type remain bound to the source image.
"""
from __future__ import annotations

import argparse
import hashlib
import lzma
import struct
import zlib
from pathlib import Path


MAGIC = 0x27051956
HEADER = 64
OEM_ARC_ARCH = 0x13
IH_COMP_NONE = 0
IH_COMP_LZMA = 3
LZMA_ALONE_HEADER = 13


def parse_header(blob: bytes) -> list[int | bytes]:
    if len(blob) < HEADER:
        raise ValueError("uImage is shorter than its legacy header")
    values = list(struct.unpack(">7I4B32s", blob[:HEADER]))
    if values[0] != MAGIC:
        raise ValueError("input is not a legacy uImage")
    header = bytearray(blob[:HEADER])
    header[4:8] = b"\0\0\0\0"
    if zlib.crc32(header) & 0xFFFFFFFF != values[1]:
        raise ValueError("input uImage header CRC mismatch")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_uimage", type=Path)
    parser.add_argument("lzma_payload", type=Path)
    parser.add_argument("output_uimage", type=Path)
    args = parser.parse_args()

    source = args.source_uimage.read_bytes()
    values = parse_header(source)
    source_size = int(values[3])
    if len(source) != HEADER + source_size:
        raise ValueError("source uImage size does not match ih_size")
    if int(values[10]) != IH_COMP_NONE:
        raise ValueError("source Q1 uImage must be uncompressed")
    raw = source[HEADER:]
    if zlib.crc32(raw) & 0xFFFFFFFF != int(values[6]):
        raise ValueError("source uImage payload CRC mismatch")

    encoded = args.lzma_payload.read_bytes()
    if len(encoded) < LZMA_ALONE_HEADER:
        raise ValueError("LZMA-alone payload is shorter than its header")
    # Bootbase's 32-bit LZMA decoder rejects an unknown/all-ones size.  The
    # legacy Quantenna encoder records the exact little-endian output size.
    declared_size = int.from_bytes(encoded[5:13], "little")
    if declared_size != len(raw):
        raise ValueError(
            f"LZMA declared size {declared_size} does not match Q1 payload {len(raw)}"
        )
    decoded = lzma.decompress(encoded, format=lzma.FORMAT_ALONE)
    if decoded != raw:
        raise ValueError("LZMA round-trip differs from exact Q1 payload")

    values[1] = 0
    values[3] = len(encoded)
    values[6] = zlib.crc32(encoded) & 0xFFFFFFFF
    values[8] = OEM_ARC_ARCH
    values[10] = IH_COMP_LZMA
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    output = struct.pack(">7I4B32s", *values) + encoded

    verify = bytearray(output[:HEADER])
    verify[4:8] = b"\0\0\0\0"
    if zlib.crc32(verify) & 0xFFFFFFFF != int(values[1]):
        raise AssertionError("output header CRC verification failed")
    if zlib.crc32(output[HEADER:]) & 0xFFFFFFFF != int(values[6]):
        raise AssertionError("output payload CRC verification failed")

    args.output_uimage.parent.mkdir(parents=True, exist_ok=True)
    args.output_uimage.write_bytes(output)
    print(
        "OMQ1_LZMA_UIMAGE_PASS "
        f"compressed_bytes={len(encoded)} decompressed_bytes={len(raw)} "
        f"decompressed_sha256={hashlib.sha256(raw).hexdigest()} "
        f"load=0x{int(values[4]):08x} entry=0x{int(values[5]):08x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
