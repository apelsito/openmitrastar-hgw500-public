#!/usr/bin/env python3
"""Stream and validate resumable Topaz md.l physical-flash captures."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

RAM_ADDRESS = 0x83000000
PHYSICAL_FLASH_SIZE = 0x1000000
READ_COMMAND = re.compile(
    r"spi_flash\s+read\s+0x([0-9a-fA-F]+)\s+0x83000000\s+0x([0-9a-fA-F]+)", re.I
)
MD_LINE = re.compile(r"^\s*(?:0x)?([0-9a-fA-F]{8})\s*:\s*(.*)$")
HEX_WORD = re.compile(r"^[0-9a-fA-F]{8}$")
EXPECTED_LAYOUT = (
    (0, "uboot", 0x000000, 0x020000),
    (1, "uboot_env", 0x020000, 0x010000),
    (2, "uboot_env_bak", 0x030000, 0x010000),
    (3, "linux_safety", 0x040000, 0x7A0000),
    (4, "linux_live", 0x7E0000, 0x7A0000),
    (5, "data", 0xF80000, 0x080000),
)


class ParseError(RuntimeError):
    pass


@dataclass
class Record:
    flash_offset: int
    requested_size: int
    data: bytearray
    valid_addresses: bool = True
    expected_address: int = RAM_ADDRESS
    source: str = ""

    @property
    def complete(self) -> bool:
        return self.valid_addresses and len(self.data) == self.requested_size


def integer(text: str) -> int:
    return int(text, 0)


def hash_file(path: Path) -> dict[str, object]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            sha256.update(block)
            md5.update(block)
    return {"size": size, "sha256": sha256.hexdigest(), "md5": md5.hexdigest()}


def parse_words(text: str) -> list[int]:
    words: list[int] = []
    for token in text.split():
        if not HEX_WORD.fullmatch(token):
            break
        words.append(int(token, 16))
        if len(words) == 4:
            break
    return words


def iter_records(path: Path) -> Iterator[Record]:
    current: Record | None = None
    with path.open("r", encoding="utf-8", errors="replace", newline="") as source:
        for line in source:
            command = READ_COMMAND.search(line)
            if command:
                if current is not None:
                    yield current
                current = Record(
                    flash_offset=int(command.group(1), 16),
                    requested_size=int(command.group(2), 16),
                    data=bytearray(),
                    source=str(path),
                )
                continue
            if current is None:
                continue
            match = MD_LINE.match(line.rstrip("\r\n"))
            if not match:
                continue
            words = parse_words(match.group(2))
            if len(words) != 4:
                current.valid_addresses = False
                continue
            address = int(match.group(1), 16)
            if address != current.expected_address:
                current.valid_addresses = False
                continue
            for word in words:
                current.data.extend(struct.pack("<I", word))
            current.expected_address += 16
        if current is not None:
            yield current


def capture_logs(capture_dir: Path, index: int, name: str) -> list[Path]:
    paths: list[Path] = []
    aggregate = capture_dir / f"mtd{index}-{name}.uart.log"
    if aggregate.is_file():
        paths.append(aggregate)
    chunk_dir = capture_dir / "chunks" / f"mtd{index}-{name}"
    if chunk_dir.is_dir():
        paths.extend(sorted(chunk_dir.glob("chunk-*.uart.log")))
    return paths


def contiguous_records(
    paths: list[Path], partition_offset: int, partition_size: int
) -> Iterator[Record]:
    expected = partition_offset
    accepted: dict[tuple[int, int], str] = {}
    for path in paths:
        for record in iter_records(path):
            if not record.complete:
                continue
            if record.flash_offset < partition_offset:
                continue
            if record.flash_offset + record.requested_size > partition_offset + partition_size:
                continue
            key = (record.flash_offset, record.requested_size)
            digest = hashlib.sha256(record.data).hexdigest()
            if key in accepted and accepted[key] != digest:
                raise ParseError(
                    f"conflicting complete captures at 0x{record.flash_offset:08x}"
                )
            accepted[key] = digest
            if record.flash_offset == expected:
                yield record
                expected += record.requested_size


def contiguous_bytes(paths: list[Path], offset: int, size: int) -> int:
    return sum(record.requested_size for record in contiguous_records(paths, offset, size))


def reconstruct_partition(
    paths: list[Path], output_path: Path, offset: int, size: int, label: str
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    chunks = 0
    sources: set[str] = set()
    with output_path.open("wb") as output:
        for record in contiguous_records(paths, offset, size):
            output.write(record.data)
            total += len(record.data)
            chunks += 1
            sources.add(record.source)
    if total != size:
        output_path.unlink(missing_ok=True)
        raise ParseError(f"{label}: reconstructed {total} bytes, expected {size}")
    result = hash_file(output_path)
    result.update({"chunks": chunks, "file": output_path.name, "source_logs": sorted(sources)})
    return result


def reconstruct_prefix(paths: list[Path], output_path: Path, offset: int, size: int) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    chunks = 0
    with output_path.open("wb") as output:
        for record in contiguous_records(paths, offset, size):
            output.write(record.data)
            total += len(record.data)
            chunks += 1
    result = hash_file(output_path)
    result.update({"chunks": chunks, "file": output_path.name, "complete": total == size})
    return result


def validate_session(session: dict[str, object]) -> list[dict[str, object]]:
    if session.get("read_only") is not True or session.get("mtd6_excluded") is not True:
        raise ParseError("session is not an mtd6-excluding read-only capture")
    if int(session.get("physical_flash_size", 0)) != PHYSICAL_FLASH_SIZE:
        raise ParseError("unexpected physical flash size")
    raw_parts = session.get("partitions")
    if not isinstance(raw_parts, list):
        raise ParseError("capture session has no partition list")
    parts = [dict(item) for item in raw_parts if isinstance(item, dict)]
    expected = [
        {"index": i, "name": n, "offset": o, "size": s} for i, n, o, s in EXPECTED_LAYOUT
    ]
    if parts != expected:
        raise ParseError("capture does not contain the exact physical mtd0..mtd5 layout")
    return parts


def load_session(capture_dir: Path) -> list[dict[str, object]]:
    path = capture_dir / "capture-session.json"
    if not path.is_file():
        raise ParseError(f"missing {path}")
    return validate_session(json.loads(path.read_text(encoding="utf-8-sig")))


def baseline_file(baseline_dir: Path, index: int) -> Path | None:
    candidates = (
        baseline_dir / f"hgw500_mtdblock{index}.bin",
        baseline_dir / "work" / "firmware_dump" / f"hgw500_mtdblock{index}.bin",
    )
    return next((path for path in candidates if path.is_file()), None)


def validate_chunk_log(path: Path, flash_offset: int, size: int) -> None:
    valid = [
        record for record in iter_records(path)
        if record.flash_offset == flash_offset and record.requested_size == size and record.complete
    ]
    if len(valid) != 1:
        details = [
            f"offset=0x{r.flash_offset:x},requested={r.requested_size},actual={len(r.data)},addresses={r.valid_addresses}"
            for r in iter_records(path)
        ]
        raise ParseError("chunk log is incomplete or ambiguous: " + "; ".join(details))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--progress-json", action="store_true")
    parser.add_argument("--partition-index", type=int)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--validate-chunk-log", type=Path)
    parser.add_argument("--flash-offset", type=integer)
    parser.add_argument("--size", type=integer)
    args = parser.parse_args()

    if args.validate_chunk_log:
        if args.flash_offset is None or args.size is None:
            raise ParseError("--validate-chunk-log requires --flash-offset and --size")
        validate_chunk_log(args.validate_chunk_log, args.flash_offset, args.size)
        print(f"CHUNK_LOG_PASS offset=0x{args.flash_offset:08x} size={args.size}")
        return 0
    if args.capture_dir is None:
        raise ParseError("--capture-dir is required")
    capture_dir = args.capture_dir.resolve()
    parts = load_session(capture_dir)

    if args.progress_json:
        progress: dict[str, object] = {}
        for part in parts:
            index, name = int(part["index"]), str(part["name"])
            done = contiguous_bytes(
                capture_logs(capture_dir, index, name), int(part["offset"]), int(part["size"])
            )
            progress[f"mtd{index}"] = {
                "name": name,
                "contiguous_bytes": done,
                "size": int(part["size"]),
                "complete": done == int(part["size"]),
                "next_flash_offset": int(part["offset"]) + done,
            }
        print(json.dumps(progress, separators=(",", ":")))
        return 0

    output_dir = (args.output_dir or (capture_dir / "reconstructed")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.partition_index is not None:
        selected = [p for p in parts if int(p["index"]) == args.partition_index]
        if len(selected) != 1:
            raise ParseError("--partition-index must select physical mtd0..mtd5")
        part = selected[0]
        index, name = int(part["index"]), str(part["name"])
        output_path = output_dir / f"hgw500_mtdblock{index}.bin"
        logs = capture_logs(capture_dir, index, name)
        if args.allow_partial:
            evidence = reconstruct_prefix(
                logs, output_path, int(part["offset"]), int(part["size"])
            )
        else:
            evidence = reconstruct_partition(
                logs, output_path, int(part["offset"]), int(part["size"]), f"mtd{index}/{name}"
            )
        print(
            f"PARSE_PARTITION_PASS mtd={index} name={name} "
            f"size={evidence['size']} sha256={evidence['sha256']} file={output_path}"
        )
        return 0
    manifest_parts: list[dict[str, object]] = []
    for part in parts:
        index, name = int(part["index"]), str(part["name"])
        output_path = output_dir / f"hgw500_mtdblock{index}.bin"
        logs = capture_logs(capture_dir, index, name)
        evidence = reconstruct_partition(
            logs, output_path, int(part["offset"]), int(part["size"]), f"mtd{index}/{name}"
        )
        entry: dict[str, object] = {**part, **evidence, "exact_size": True}
        if args.baseline_dir:
            baseline = baseline_file(args.baseline_dir.resolve(), index)
            if baseline:
                baseline_hash = hash_file(baseline)
                entry["baseline"] = {
                    "file": str(baseline), **baseline_hash,
                    "byte_identical": baseline_hash["size"] == evidence["size"] and baseline_hash["sha256"] == evidence["sha256"],
                }
        manifest_parts.append(entry)
        print(f"PARSE_PARTITION_PASS mtd={index} name={name} size={evidence['size']} sha256={evidence['sha256']}")

    physical_path = output_dir / "hgw500_physical_16m_current_unit.bin"
    with physical_path.open("wb") as combined:
        for part in manifest_parts:
            with (output_dir / str(part["file"])).open("rb") as source:
                shutil.copyfileobj(source, combined, length=1024 * 1024)
    physical = hash_file(physical_path)
    if physical["size"] != PHYSICAL_FLASH_SIZE:
        raise ParseError(f"physical image is {physical['size']} bytes")
    manifest = {
        "schema": "openmitrastar.physical-flash-backup.v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_capture": str(capture_dir), "read_only_capture": True,
        "physical_layout": "mtd0..mtd5 contiguous, exactly 16 MiB",
        "mtd6_included": False,
        "mtd6_reason": "logical rootfs view inside linux_live; not physical flash",
        "partitions": manifest_parts,
        "physical_image": {"file": physical_path.name, **physical},
        "validation": {"all_partition_sizes_exact": True, "all_physical_partitions_present": True, "physical_size_exact": True},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sums = [f"{p['sha256']}  {p['file']}" for p in manifest_parts]
    sums.append(f"{physical['sha256']}  {physical_path.name}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
    print(f"PHYSICAL_BACKUP_PASS size={physical['size']} sha256={physical['sha256']} manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ParseError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PHYSICAL_BACKUP_FAIL error={exc}", file=sys.stderr)
        raise SystemExit(1)
