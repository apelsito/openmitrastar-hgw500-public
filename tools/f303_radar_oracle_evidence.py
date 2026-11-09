#!/usr/bin/env python3
"""Offline contracts and evidence handling for the F303 OEM radar oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


VECTOR_SCHEMA = "openmitrastar.f303-radar-vector/v1"
COMMAND_SCHEMA = "openmitrastar.f303-radar-oracle-commands/v1"
MANIFEST_SCHEMA = "openmitrastar.f303-radar-oracle-evidence-manifest/v1"

SAFE_PREFIXES = (
    "OMRADAR_",
    "OMF301_",
    "BOOTBASE_",
)
SAFE_BOOT_PATTERNS = (
    re.compile(r"^Read: flash=0x(?:40000|7e0000) mem=0x83000000 size=7995392 ret_size=7995392$"),
    re.compile(r"^\s*Verifying Checksum\s+\.\.\.\s+OK\s*$"),
    re.compile(r"^Linux version (?:2\.6\.35\.12|5\.10\.260-openmitrastar-radiohw)\b"),
    re.compile(r"^VFS: Mounted root \(squashfs filesystem\) readonly\b"),
)
SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\b(?:psk|passphrase|password|private[_ -]?key|secret|calibration)\b"),
    re.compile(r"(?i)\b(?:wifiaddr|ethaddr|serialnumber|base[_ -]?mac)\b"),
    re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}"),
    re.compile(r"(?i)\b(?:txpower\.cal|dc_iq(?:_2g)?\.cal|pdetector(?:_2g)?\.cal)\b"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _word(value: Any) -> int:
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{1,8}", value):
        number = int(value, 16)
    else:
        raise ValueError(f"invalid 32-bit word: {value!r}")
    if not 0 <= number <= 0xFFFFFFFF:
        raise ValueError(f"word outside uint32: {value!r}")
    return number


def validate_vector(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != VECTOR_SCHEMA:
        raise ValueError("unexpected radar vector schema")
    if payload.get("source") != "synthetic":
        raise ValueError("physical capture accepts only a pre-reviewed synthetic vector")
    if payload.get("region") != "eu":
        raise ValueError("F303 OEM oracle requires the normalized EU region")
    channel = payload.get("channel")
    bandwidth = payload.get("bandwidth_mhz")
    if channel not in {100, 104, 108, 112}:
        raise ValueError("oracle channel must be a non-weather ETSI DFS channel")
    if bandwidth not in {20, 40, 80}:
        raise ValueError("bandwidth must be 20, 40 or 80 MHz")
    fifo = payload.get("fifo")
    if not isinstance(fifo, dict):
        raise ValueError("fifo object is required")
    high = fifo.get("mem_h_words")
    low = fifo.get("mem_l_words")
    if not isinstance(high, list) or not isinstance(low, list):
        raise ValueError("both pulse banks must be arrays")
    if not high or len(high) != len(low) or len(high) > 64:
        raise ValueError("pulse banks must contain 1..64 paired words")
    pairs = [(_word(h), _word(l)) for h, l in zip(high, low, strict=True)]
    return {
        "name": str(payload.get("name", "")),
        "source": "synthetic",
        "region": "eu",
        "channel": channel,
        "bandwidth_mhz": bandwidth,
        "pulse_count": len(pairs),
        "pairs": pairs,
    }


def build_oracle_commands(payload: dict[str, Any]) -> dict[str, Any]:
    vector = validate_vector(payload)
    commands = ["echo tstart > /proc/radar"]
    for high, low in vector["pairs"]:
        commands.append(f"echo 'tdata:{high:08x} - {low:08x}' > /proc/radar")
    commands.append("echo tend > /proc/radar")
    return {
        "schema": COMMAND_SCHEMA,
        "vector_name": vector["name"],
        "source": vector["source"],
        "region": vector["region"],
        "channel": vector["channel"],
        "bandwidth_mhz": vector["bandwidth_mhz"],
        "pulse_count": vector["pulse_count"],
        "commands": commands,
    }


def sanitize_line(line: str) -> str | None:
    normalized = line.replace("\x00", "").strip("\r\n")
    if not normalized:
        return None
    if any(pattern.search(normalized) for pattern in SENSITIVE_PATTERNS):
        return None
    if normalized.startswith(SAFE_PREFIXES):
        return normalized
    if any(pattern.match(normalized) for pattern in SAFE_BOOT_PATTERNS):
        return normalized.strip()
    return None


def sanitize_file(source: Path, destination: Path) -> int:
    kept: list[str] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        safe = sanitize_line(line)
        if safe is not None:
            kept.append(safe)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(f"{line}\n" for line in kept), encoding="ascii")
    return len(kept)


def build_manifest(directory: Path, output: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    output_resolved = output.resolve()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        if path.resolve() == output_resolved:
            continue
        records.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    payload = {
        "schema": MANIFEST_SCHEMA,
        "files": records,
        "file_count": len(records),
        "raw_uart_retained": False,
        "sensitive_material_retained": False,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    vector_parser = sub.add_parser("vector")
    vector_parser.add_argument("--input", type=Path, required=True)
    vector_parser.add_argument("--output", type=Path, required=True)

    sanitize_parser = sub.add_parser("sanitize")
    sanitize_parser.add_argument("--input", type=Path, required=True)
    sanitize_parser.add_argument("--output", type=Path, required=True)

    manifest_parser = sub.add_parser("manifest")
    manifest_parser.add_argument("--directory", type=Path, required=True)
    manifest_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "vector":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = build_oracle_commands(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "sanitize":
        count = sanitize_file(args.input, args.output)
        print(json.dumps({"kept_lines": count, "output": str(args.output)}, sort_keys=True))
        return 0
    if args.command == "manifest":
        result = build_manifest(args.directory, args.output)
        print(json.dumps(result, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
