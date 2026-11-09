#!/usr/bin/env python3
"""Build a full 16 MiB SPI image with one firmware slot replaced.

This is for CH341A recovery/test cycles.  It never invents calibration data:
the base image supplies bootloader, both env slots, the untouched firmware
slot and mtd5.  The selected slot is replaced by a checked webformat/uImage
payload padded with 0xff to the exact partition size.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path


FLASH_SIZE = 0x1000000
SLOT_SIZE = 0x7A0000
PARTS = {
    "uboot_env": (0x020000, 0x010000),
    "uboot_env_bak": (0x030000, 0x010000),
    "linux_safety": (0x040000, SLOT_SIZE),
    "linux_live": (0x7E0000, SLOT_SIZE),
}
UIMAGE_MAGIC = 0x27051956
RAS_PAYLOAD_OFFSET = 0x2000
OEM_ARC_ARCH = 0x13


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_candidate(data: bytes) -> dict[str, int | str | bool]:
    if len(data) < 64:
        raise ValueError("candidate is shorter than a uImage header")
    if len(data) > SLOT_SIZE:
        raise ValueError(f"candidate is larger than slot: {len(data)} > {SLOT_SIZE}")

    magic, hcrc, timestamp, size, load, entry, dcrc, os_, arch, typ, comp, name = (
        struct.unpack(">7I4B32s", data[:64])
    )
    if magic != UIMAGE_MAGIC:
        raise ValueError(f"bad uImage magic: 0x{magic:08x}")
    if arch != OEM_ARC_ARCH:
        raise ValueError(f"candidate arch is 0x{arch:02x}, expected OEM ARC 0x13")
    payload_end = RAS_PAYLOAD_OFFSET + size
    if payload_end > len(data):
        raise ValueError(
            f"payload size exceeds candidate: header payload={size}, file={len(data)}"
        )

    header = bytearray(data[:64])
    header[4:8] = b"\0\0\0\0"
    hcrc_ok = (zlib.crc32(header) & 0xFFFFFFFF) == hcrc
    dcrc_ok = (zlib.crc32(data[RAS_PAYLOAD_OFFSET:payload_end]) & 0xFFFFFFFF) == dcrc
    if not hcrc_ok or not dcrc_ok:
        raise ValueError(f"candidate CRC failure: hcrc_ok={hcrc_ok} dcrc_ok={dcrc_ok}")

    return {
        "file_size": len(data),
        "payload_size": size,
        "load": f"0x{load:08x}",
        "entry": f"0x{entry:08x}",
        "os": f"0x{os_:02x}",
        "arch": f"0x{arch:02x}",
        "type": f"0x{typ:02x}",
        "compression": f"0x{comp:02x}",
        "name": name.rstrip(b"\0").decode("ascii", "replace"),
        "hcrc_ok": hcrc_ok,
        "dcrc_ok": dcrc_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--target", required=True, choices=["linux_safety", "linux_live"])
    parser.add_argument("--env", type=Path, help="optional 64 KiB env image for both env copies")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    base = args.base.read_bytes()
    if len(base) != FLASH_SIZE:
        raise ValueError(f"base image must be 16 MiB, got {len(base)} bytes")
    candidate = args.candidate.read_bytes()
    candidate_info = validate_candidate(candidate)

    image = bytearray(base)
    if args.env:
        env = args.env.read_bytes()
        if len(env) != PARTS["uboot_env"][1]:
            raise ValueError(f"env must be 64 KiB, got {len(env)} bytes")
        for name in ("uboot_env", "uboot_env_bak"):
            start, size = PARTS[name]
            image[start:start + size] = env

    start, size = PARTS[args.target]
    slot = candidate + (b"\xff" * (size - len(candidate)))
    image[start:start + size] = slot

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)

    manifest = {
        "output": str(args.output),
        "output_size": len(image),
        "output_sha256": sha256(args.output),
        "base": str(args.base),
        "base_sha256": sha256(args.base),
        "candidate": str(args.candidate),
        "candidate_sha256": sha256(args.candidate),
        "candidate_info": candidate_info,
        "target": args.target,
        "target_offset": f"0x{start:06x}",
        "target_size": f"0x{size:06x}",
        "env": str(args.env) if args.env else None,
        "env_sha256": sha256(args.env) if args.env else None,
        "preserved_partitions": [
            name for name in PARTS if name not in {args.target, "uboot_env", "uboot_env_bak"}
        ] + ["uboot", "data"],
    }
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
