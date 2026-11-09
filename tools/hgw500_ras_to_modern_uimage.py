"""Convert HGW500 OEM RAS to upstream ARC uImage, without changing payload.

File-only preparation for U-Boot 2026.10 RAM second-stage experiments.
Output is not an OEM Bootbase/flash image. Original input is read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

MAGIC = 0x27051956
RAS_OFFSET = 0x2000
OEM_ARC = 19
UPSTREAM_ARC = 23
LOW = 0x8493A000
HIGH = 0x86000000  # Do not overwrite the diagnostic second stage's linked image.
MAX_UNCOMPRESSED = HIGH - LOW


def convert(data: bytes) -> tuple[bytes, dict]:
    if len(data) < RAS_OFFSET:
        raise ValueError("truncated RAS header/padding")
    magic, hcrc, stamp, size, load, entry, dcrc, os_id, arch, kind, comp, name = struct.unpack(">7I4B32s", data[:64])
    if magic != MAGIC:
        raise ValueError("invalid image magic")
    header = bytearray(data[:64])
    header[4:8] = bytes(4)
    if zlib.crc32(header) & 0xFFFFFFFF != hcrc:
        raise ValueError("invalid original header CRC")
    if (os_id, arch, kind) != (5, OEM_ARC, 2) or comp != 0:
        raise ValueError("unsupported OEM image architecture/type/compression")
    if not size or RAS_OFFSET + size > len(data):
        raise ValueError("truncated or empty RAS payload")
    payload = data[RAS_OFFSET:RAS_OFFSET + size]
    if zlib.crc32(payload) & 0xFFFFFFFF != dcrc:
        raise ValueError("invalid original payload CRC")
    # The integrated Linux 7.3 RAM input is uncompressed. Compressed legacy
    # input needs a separately qualified decoder/range contract before use.
    decoded_size = len(payload)
    if not LOW <= load < HIGH or decoded_size > HIGH - load:
        raise ValueError("image overlaps second stage or lies outside qualified DDR")
    if not load <= entry < load + decoded_size or entry & 3:
        raise ValueError("entry outside aligned loaded payload")
    header[29] = UPSTREAM_ARC
    struct.pack_into(">I", header, 4, zlib.crc32(header) & 0xFFFFFFFF)
    result = bytes(header) + payload
    return result, {
        "status": "PASS_OFFLINE_FORMAT_CONVERSION_NO_GO_HARDWARE",
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "output_sha256": hashlib.sha256(result).hexdigest(),
        "input_bytes": len(data), "output_bytes": len(result),
        "payload_bytes": len(payload), "decoded_bytes": decoded_size,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "payload_unchanged": result[64:] == payload,
        "load": hex(load), "entry": hex(entry), "load_end": hex(load + decoded_size),
        "old_payload_offset": hex(RAS_OFFSET), "new_payload_offset": "0x40",
        "old_arch": OEM_ARC, "new_arch": UPSTREAM_ARC,
        "compression": "none; compressed OEM inputs explicitly rejected by v1",
        "changed_fields": ["header CRC", "architecture identifier", "container padding removed"],
        "oem_flash_eligible": False, "hardware_accessed": False,
        "limits": "format/range/checksum conversion only; not Linux boot, external DTB, recovery or persistent acceptance",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    data = args.input.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.sha256:
        raise ValueError("input hash mismatch")
    if args.output.resolve() == args.input.resolve():
        raise ValueError("output must differ from original")
    output, result = convert(data)
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt = args.output.with_suffix(args.output.suffix + ".json")
    if args.output.exists() or receipt.exists():
        raise FileExistsError("output/receipt exists; select a new version")
    with args.output.open("xb") as stream:
        stream.write(output)
    args.output.chmod(0o600)
    receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    receipt.chmod(0o600)
    if hashlib.sha256(args.input.read_bytes()).hexdigest() != args.sha256:
        raise ValueError("original changed during conversion")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
