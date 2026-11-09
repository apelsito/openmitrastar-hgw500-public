#!/usr/bin/env python3
"""Offline Bootbase contract emulator for the HGW-500BNA-QCv2.

This is not a CPU emulator. It models the safety-critical Bootbase contract we
can prove from stock images and live environment dumps:

* redundant U-Boot environment CRC and bootselect selection;
* physical slot layout for linux_safety/linux_live;
* OEM RAS/uImage validation: header at 0x0, payload CRC over offset 0x2000;
* selected-slot then fallback-slot decision flow.

The tool is intentionally read-only and never writes flash images.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import lzma
import struct
import sys
import zlib
from pathlib import Path
from typing import Any


ENV_DATA_SIZE = 0x6000
FLASH_SIZE = 0x01000000
UIMAGE_MAGIC = 0x27051956
UIMAGE_HEADER_SIZE = 64
RAS_PAYLOAD_OFFSET = 0x2000
OEM_ARC_ARCH = 0x13


PARTITIONS = {
    "uboot": (0x000000, 0x020000),
    "uboot_env": (0x020000, 0x010000),
    "uboot_env_bak": (0x030000, 0x010000),
    "linux_safety": (0x040000, 0x7A0000),
    "linux_live": (0x7E0000, 0x7A0000),
    "data": (0xF80000, 0x080000),
}

PART_FILENAMES = {
    "uboot": "hgw500_mtdblock0.bin",
    "uboot_env": "hgw500_mtdblock1.bin",
    "uboot_env_bak": "hgw500_mtdblock2.bin",
    "linux_safety": "hgw500_mtdblock3.bin",
    "linux_live": "hgw500_mtdblock4.bin",
    "data": "hgw500_mtdblock5.bin",
}


@dataclasses.dataclass
class EnvResult:
    source: str
    valid_crc: bool
    stored_crc: int
    calculated_crc: int
    values: dict[str, str]
    error: str | None = None


@dataclasses.dataclass
class ImageResult:
    source: str
    accepted_by_contract: bool
    kind: str
    errors: list[str]
    warnings: list[str]
    header: dict[str, Any] | None
    sha256: str
    size: int


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_parts(args: argparse.Namespace) -> dict[str, bytes]:
    if args.flash:
        blob = args.flash.read_bytes()
        if len(blob) != FLASH_SIZE:
            raise SystemExit(
                f"{args.flash} is {len(blob)} bytes, expected physical 16 MiB "
                f"({FLASH_SIZE} bytes). Do not pass an mtd0-mtd6 concatenation."
            )
        return {
            name: blob[offset : offset + size]
            for name, (offset, size) in PARTITIONS.items()
        }

    if not args.parts_dir:
        raise SystemExit("pass --parts-dir or --flash")
    base = args.parts_dir
    parts = {}
    for name, filename in PART_FILENAMES.items():
        path = base / filename
        if not path.exists():
            raise SystemExit(f"missing partition file: {path}")
        data = path.read_bytes()
        expected = PARTITIONS[name][1]
        if len(data) != expected:
            raise SystemExit(f"{path} is {len(data)} bytes, expected {expected}")
        parts[name] = data
    return parts


def parse_env(source: str, data: bytes) -> EnvResult:
    if len(data) < ENV_DATA_SIZE:
        return EnvResult(source, False, 0, 0, {}, "environment partition too small")

    stored = struct.unpack_from("<I", data, 0)[0]
    calc = zlib.crc32(data[4:ENV_DATA_SIZE]) & 0xFFFFFFFF
    values: dict[str, str] = {}
    error = None

    try:
        for raw in data[4:ENV_DATA_SIZE].split(b"\0"):
            if not raw:
                break
            if b"=" not in raw:
                raise ValueError(f"malformed env entry: {raw[:32]!r}")
            key, value = raw.split(b"=", 1)
            values[key.decode("ascii")] = value.decode("ascii")
    except Exception as exc:  # noqa: BLE001 - reporting verifier context
        error = str(exc)

    return EnvResult(source, stored == calc and error is None, stored, calc, values, error)


def parse_uimage_header(data: bytes) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if len(data) < UIMAGE_HEADER_SIZE:
        return None, ["image shorter than uImage header"]

    fields = struct.unpack(">7I4B32s", data[:UIMAGE_HEADER_SIZE])
    magic, hcrc, timestamp, size, load, entry, dcrc = fields[:7]
    os_id, arch, image_type, comp, name_raw = fields[7:]
    if magic != UIMAGE_MAGIC:
        errors.append(f"bad uImage magic 0x{magic:08x}")

    header_zero = bytearray(data[:UIMAGE_HEADER_SIZE])
    header_zero[4:8] = b"\0\0\0\0"
    calc_hcrc = zlib.crc32(header_zero) & 0xFFFFFFFF
    if hcrc != calc_hcrc:
        errors.append(f"bad header CRC stored=0x{hcrc:08x} calculated=0x{calc_hcrc:08x}")

    name = name_raw.split(b"\0", 1)[0].decode("ascii", "replace")
    return {
        "magic": f"0x{magic:08x}",
        "hcrc": f"0x{hcrc:08x}",
        "calculated_hcrc": f"0x{calc_hcrc:08x}",
        "timestamp": timestamp,
        "payload_size": size,
        "load": f"0x{load:08x}",
        "entry": f"0x{entry:08x}",
        "dcrc": f"0x{dcrc:08x}",
        "os": os_id,
        "arch": arch,
        "type": image_type,
        "compression": comp,
        "name": name,
    }, errors


def validate_bootbase_slot(source: str, data: bytes, slot_size: int) -> ImageResult:
    errors: list[str] = []
    warnings: list[str] = []
    header, header_errors = parse_uimage_header(data)
    errors.extend(header_errors)

    if header is None:
        return ImageResult(source, False, "unknown", errors, warnings, None, sha256(data), len(data))

    payload_size = int(header["payload_size"])
    payload_end = RAS_PAYLOAD_OFFSET + payload_size
    if payload_end > len(data):
        errors.append(
            f"RAS payload exceeds file: end=0x{payload_end:x} file=0x{len(data):x}"
        )
    if payload_end > slot_size:
        errors.append(
            f"RAS payload exceeds slot: end=0x{payload_end:x} slot=0x{slot_size:x}"
        )

    arch = int(header["arch"])
    if arch != OEM_ARC_ARCH:
        errors.append(f"Bootbase OEM ARC arch must be 0x13, got 0x{arch:02x}")

    if int(header["os"]) != 5:
        errors.append(f"unexpected OS id {header['os']}, expected Linux/5")
    if int(header["type"]) != 2:
        errors.append(f"unexpected image type {header['type']}, expected kernel/2")
    if int(header["compression"]) not in (0, 3):
        errors.append(
            f"unexpected compression {header['compression']}, expected none/0 or lzma/3"
        )

    if len(data) >= RAS_PAYLOAD_OFFSET and payload_end <= len(data):
        payload = data[RAS_PAYLOAD_OFFSET:payload_end]
        calc_dcrc = zlib.crc32(payload) & 0xFFFFFFFF
        stored_dcrc = int(str(header["dcrc"]), 16)
        header["calculated_ras_payload_dcrc"] = f"0x{calc_dcrc:08x}"
        if calc_dcrc != stored_dcrc:
            errors.append(
                "bad RAS payload CRC "
                f"stored=0x{stored_dcrc:08x} calculated=0x{calc_dcrc:08x}"
            )
        if int(header["compression"]) == 3:
            if len(payload) < 13:
                errors.append("LZMA-alone payload shorter than 13-byte header")
            else:
                declared_size = int.from_bytes(payload[5:13], "little")
                dictionary_size = int.from_bytes(payload[1:5], "little")
                header["lzma_declared_uncompressed_size"] = declared_size
                header["lzma_dictionary_size"] = dictionary_size
                # The OEM U-Boot LzmaTools.c uses a 32-bit SizeT and rejects
                # an unknown/all-ones or otherwise non-zero high word.
                if declared_size > 0xFFFFFFFF:
                    errors.append(
                        "LZMA declared size is not representable by Bootbase's 32-bit decoder"
                    )
                else:
                    try:
                        decoded = lzma.decompress(payload, format=lzma.FORMAT_ALONE)
                    except lzma.LZMAError as exc:
                        errors.append(f"LZMA-alone payload does not decode: {exc}")
                    else:
                        header["lzma_decompressed_size"] = len(decoded)
                        header["lzma_decompressed_sha256"] = sha256(decoded)
                        if len(decoded) != declared_size:
                            errors.append(
                                "LZMA decoded size differs from declared size: "
                                f"decoded={len(decoded)} declared={declared_size}"
                            )
    else:
        errors.append("cannot calculate RAS payload CRC")

    if len(data) == UIMAGE_HEADER_SIZE + payload_size:
        warnings.append(
            "standard uImage shape detected; Bootbase slot expects OEM RAS payload at 0x2000"
        )

    kind = "bootbase-oem-ras-slot" if not errors else "rejected-slot"
    return ImageResult(source, not errors, kind, errors, warnings, header, sha256(data), len(data))


def decide_boot(env: dict[str, str], safety: ImageResult, live: ImageResult) -> dict[str, Any]:
    bootselect = env.get("bootselect")
    selected = "linux_live" if bootselect == "0" else "linux_safety"
    fallback = "linux_safety" if selected == "linux_live" else "linux_live"
    results = {"linux_safety": safety, "linux_live": live}

    attempts = []
    for name in (selected, fallback):
        image = results[name]
        attempts.append(
            {
                "slot": name,
                "accepted_by_contract": image.accepted_by_contract,
                "errors": image.errors,
            }
        )
        if image.accepted_by_contract:
            return {
                "bootselect": bootselect,
                "selected_slot": selected,
                "fallback_slot": fallback,
                "attempts": attempts,
                "would_handoff": True,
                "handoff_slot": name,
                "note": "This proves Bootbase-format acceptance only, not Linux runtime boot.",
            }

    return {
        "bootselect": bootselect,
        "selected_slot": selected,
        "fallback_slot": fallback,
        "attempts": attempts,
        "would_handoff": False,
        "handoff_slot": None,
        "note": "Both slots fail the offline Bootbase contract.",
    }


def image_to_dict(image: ImageResult) -> dict[str, Any]:
    return {
        "source": image.source,
        "accepted_by_contract": image.accepted_by_contract,
        "kind": image.kind,
        "size": image.size,
        "sha256": image.sha256,
        "header": image.header,
        "warnings": image.warnings,
        "errors": image.errors,
    }


def env_to_dict(env: EnvResult) -> dict[str, Any]:
    interesting = [
        "bootcmd",
        "bootselect",
        "safety_image_addr",
        "safety_image_size",
        "live_image_addr",
        "live_image_size",
        "loadaddr",
        "bootargs",
    ]
    return {
        "source": env.source,
        "valid_crc": env.valid_crc,
        "stored_crc": f"0x{env.stored_crc:08x}",
        "calculated_crc": f"0x{env.calculated_crc:08x}",
        "error": env.error,
        "values": {key: env.values.get(key) for key in interesting if key in env.values},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts-dir", type=Path, help="directory containing hgw500_mtdblock0..5.bin")
    parser.add_argument("--flash", type=Path, help="physical 16 MiB flash image, not mtd0-mtd6 concat")
    parser.add_argument("--candidate-slot", type=Path, help="optional image to validate as a Bootbase slot")
    parser.add_argument(
        "--candidate-name",
        default="candidate",
        help="label for --candidate-slot in the JSON report",
    )
    parser.add_argument("--json-out", type=Path, help="write full JSON report")
    args = parser.parse_args()

    parts = load_parts(args)
    primary_env = parse_env("uboot_env", parts["uboot_env"])
    backup_env = parse_env("uboot_env_bak", parts["uboot_env_bak"])

    env = primary_env if primary_env.valid_crc else backup_env
    safety = validate_bootbase_slot(
        "linux_safety", parts["linux_safety"], PARTITIONS["linux_safety"][1]
    )
    live = validate_bootbase_slot("linux_live", parts["linux_live"], PARTITIONS["linux_live"][1])
    decision = decide_boot(env.values, safety, live)

    report: dict[str, Any] = {
        "emulator": "bootbase-contract",
        "scope": [
            "U-Boot env CRC",
            "bootselect slot order",
            "OEM RAS/uImage header CRC",
            "payload CRC from offset 0x2000",
            "slot size guard",
        ],
        "non_go_scope": [
            "ARC instruction execution",
            "Bootbase proprietary code paths not represented by image contract",
            "MMU/cache/runtime Linux boot",
            "Topaz IRQ/UART/SPI/watchdog side effects",
        ],
        "environment": {
            "primary": env_to_dict(primary_env),
            "backup": env_to_dict(backup_env),
            "selected_source": env.source,
            "redundant_match": primary_env.values == backup_env.values,
        },
        "slots": {
            "linux_safety": image_to_dict(safety),
            "linux_live": image_to_dict(live),
        },
        "decision": decision,
    }

    if args.candidate_slot:
        candidate = validate_bootbase_slot(
            args.candidate_name,
            args.candidate_slot.read_bytes(),
            PARTITIONS["linux_live"][1],
        )
        report["candidate"] = image_to_dict(candidate)

    ok = (
        primary_env.valid_crc
        and backup_env.valid_crc
        and safety.accepted_by_contract
        and live.accepted_by_contract
        and decision["would_handoff"]
    )
    if "candidate" in report:
        ok = ok and bool(report["candidate"]["accepted_by_contract"])

    report["result"] = "PASS" if ok else "FAIL"

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
