#!/usr/bin/env python3
"""Safely inspect Quantenna MuC, DSP and AuC packed ELF32 firmware.

The legacy qdrv loader consumes a non-relocating ELF32 image whose segment
payloads follow the program-header table consecutively.  This module parses
that format without mapping addresses, requesting firmware, or touching MMIO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence


ELF32_EHDR_SIZE = 52
ELF32_PHDR_SIZE = 32
ELFCLASS32 = 1
ELFDATA2LSB = 1
ELFDATA2MSB = 2
EV_CURRENT = 1
EM_ARC_COMPACT = 93
PT_LOAD = 1
PF_X = 1
UINT32_LIMIT = 1 << 32
DSP_XYMEM_BEGIN = 0xD0000000
DSP_XYMEM_END_EXCLUSIVE = 0xE0000000

Cpu = Literal["muc", "dsp", "auc"]


class FirmwareFormatError(ValueError):
    """Raised when a firmware image violates the qdrv packed-ELF contract."""


@dataclass(frozen=True)
class SegmentReport:
    index: int
    file_offset: int
    payload_offset: int
    payload_size: int
    payload_sha256: str
    virtual_address: int
    physical_address: int
    load_address: int
    memory_size: int
    flags: int
    alignment: int
    skipped_by_loader: bool


@dataclass(frozen=True)
class FirmwareReport:
    source: str
    cpu: Cpu
    size: int
    sha256: str
    endian: str
    machine: int
    entry_point: int
    program_headers: int
    segments: tuple[SegmentReport, ...]
    trailer_offset: int
    trailer_size: int
    trailer_sha256: str | None


def _checked_add(left: int, right: int, limit: int, label: str) -> int:
    if left < 0 or right < 0 or left > limit or right > limit - left:
        raise FirmwareFormatError(f"{label} overflows or exceeds limit {limit}")
    return left + right


def _checked_mul(left: int, right: int, limit: int, label: str) -> int:
    if left < 0 or right < 0 or (left and right > limit // left):
        raise FirmwareFormatError(f"{label} overflows or exceeds limit {limit}")
    return left * right


def infer_cpu(name: str) -> Cpu:
    lowered = Path(name).name.lower()
    if lowered.startswith("qtn_driver"):
        return "muc"
    if lowered.startswith("rdsp_driver"):
        return "dsp"
    if lowered.startswith("auc_driver"):
        return "auc"
    raise FirmwareFormatError(
        f"cannot infer CPU from {name!r}; pass --cpu muc, dsp, or auc"
    )


def _load_address(cpu: Cpu, virtual: int, physical: int) -> tuple[int, bool]:
    if cpu == "dsp":
        skipped = DSP_XYMEM_BEGIN <= virtual < DSP_XYMEM_END_EXCLUSIVE
        return virtual, skipped
    return physical or virtual, False


def inspect_firmware(data: bytes, *, source: str, cpu: Cpu) -> FirmwareReport:
    """Parse and validate one packed ELF32 firmware image."""
    size = len(data)
    if size < ELF32_EHDR_SIZE:
        raise FirmwareFormatError(
            f"file is {size} bytes; ELF32 header needs {ELF32_EHDR_SIZE}"
        )
    if data[:4] != b"\x7fELF":
        raise FirmwareFormatError("invalid ELF magic")
    if data[4] != ELFCLASS32:
        raise FirmwareFormatError(f"unsupported ELF class {data[4]}; expected ELF32")
    if data[5] not in (ELFDATA2LSB, ELFDATA2MSB):
        raise FirmwareFormatError(f"invalid ELF data encoding {data[5]}")
    if data[5] != ELFDATA2LSB:
        raise FirmwareFormatError("unexpected big-endian firmware; target ABI is little-endian")
    if data[6] != EV_CURRENT:
        raise FirmwareFormatError(f"unsupported ELF ident version {data[6]}")

    endian = "<"
    header = struct.unpack_from(endian + "HHIIIIIHHHHHH", data, 16)
    (
        _elf_type,
        machine,
        version,
        entry,
        phoff,
        _shoff,
        _flags,
        ehsize,
        phentsize,
        phnum,
        _shentsize,
        _shnum,
        _shstrndx,
    ) = header
    if machine != EM_ARC_COMPACT:
        raise FirmwareFormatError(
            f"unexpected ELF machine {machine}; expected ARC compact {EM_ARC_COMPACT}"
        )
    if version != EV_CURRENT:
        raise FirmwareFormatError(f"unsupported ELF version {version}")
    if ehsize != ELF32_EHDR_SIZE:
        raise FirmwareFormatError(
            f"invalid ELF header size {ehsize}; expected {ELF32_EHDR_SIZE}"
        )
    if phentsize != ELF32_PHDR_SIZE:
        raise FirmwareFormatError(
            f"invalid program-header size {phentsize}; expected {ELF32_PHDR_SIZE}"
        )
    if phnum == 0:
        raise FirmwareFormatError("firmware contains no program headers")
    if phoff != ehsize:
        raise FirmwareFormatError(
            f"program-header table starts at {phoff}; packed qdrv format expects {ehsize}"
        )

    table_size = _checked_mul(phentsize, phnum, size, "program-header table")
    table_end = _checked_add(phoff, table_size, size, "program-header table")
    payload_cursor = table_end
    segments: list[SegmentReport] = []
    loaded_ranges: list[tuple[int, int, int]] = []
    executable_virtual_ranges: list[tuple[int, int]] = []

    for index in range(phnum):
        header_offset = phoff + index * phentsize
        (
            segment_type,
            file_offset,
            virtual,
            physical,
            file_size,
            memory_size,
            flags,
            alignment,
        ) = struct.unpack_from(endian + "IIIIIIII", data, header_offset)
        if segment_type != PT_LOAD:
            raise FirmwareFormatError(
                f"segment {index} has type {segment_type}; qdrv loader requires PT_LOAD"
            )
        if file_size > memory_size:
            raise FirmwareFormatError(
                f"segment {index} p_filesz {file_size} exceeds p_memsz {memory_size}"
            )
        # Zero-sized BSS-only entries in vendor images keep a stale/repeated
        # p_offset. qdrv consumes no bytes for them, so only data-bearing
        # segments have a meaningful packed payload offset.
        if file_size and file_offset != payload_cursor:
            raise FirmwareFormatError(
                f"segment {index} p_offset {file_offset} does not match packed payload "
                f"offset {payload_cursor}"
            )
        payload_end = _checked_add(
            payload_cursor, file_size, size, f"segment {index} file range"
        )
        load_address, skipped = _load_address(cpu, virtual, physical)
        load_end = _checked_add(
            load_address, memory_size, UINT32_LIMIT, f"segment {index} address range"
        )
        virtual_end = _checked_add(
            virtual, memory_size, UINT32_LIMIT, f"segment {index} virtual range"
        )
        payload = data[payload_cursor:payload_end]
        segments.append(
            SegmentReport(
                index=index,
                file_offset=file_offset,
                payload_offset=payload_cursor,
                payload_size=file_size,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
                virtual_address=virtual,
                physical_address=physical,
                load_address=load_address,
                memory_size=memory_size,
                flags=flags,
                alignment=alignment,
                skipped_by_loader=skipped,
            )
        )
        if memory_size and not skipped:
            loaded_ranges.append((load_address, load_end, index))
        if memory_size and not skipped and flags & PF_X:
            executable_virtual_ranges.append((virtual, virtual_end))
        payload_cursor = payload_end

    loaded_ranges.sort()
    for previous, current in zip(loaded_ranges, loaded_ranges[1:]):
        if current[0] < previous[1]:
            raise FirmwareFormatError(
                f"loaded segments {previous[2]} and {current[2]} overlap: "
                f"0x{previous[0]:08x}-0x{previous[1]:08x} and "
                f"0x{current[0]:08x}-0x{current[1]:08x}"
            )
    if not any(start <= entry < end for start, end in executable_virtual_ranges):
        raise FirmwareFormatError(
            f"entry point 0x{entry:08x} is outside executable segment ranges"
        )

    trailer = data[payload_cursor:]
    return FirmwareReport(
        source=source,
        cpu=cpu,
        size=size,
        sha256=hashlib.sha256(data).hexdigest(),
        endian="little",
        machine=machine,
        entry_point=entry,
        program_headers=phnum,
        segments=tuple(segments),
        trailer_offset=payload_cursor,
        trailer_size=len(trailer),
        trailer_sha256=hashlib.sha256(trailer).hexdigest() if trailer else None,
    )


def _human_report(report: FirmwareReport) -> str:
    lines = [
        f"OK {report.source}",
        f"  cpu={report.cpu} size={report.size} sha256={report.sha256}",
        f"  endian={report.endian} machine={report.machine} "
        f"entry=0x{report.entry_point:08x} phdrs={report.program_headers}",
    ]
    for segment in report.segments:
        suffix = " skipped-dsp-xymem" if segment.skipped_by_loader else ""
        lines.append(
            f"  [{segment.index}] p_offset=0x{segment.file_offset:x} "
            f"payload=0x{segment.payload_offset:x}+{segment.payload_size} "
            f"load=0x{segment.load_address:08x}+{segment.memory_size} "
            f"sha256={segment.payload_sha256}{suffix}"
        )
    if report.trailer_size:
        lines.append(
            f"  trailer=0x{report.trailer_offset:x}+{report.trailer_size} "
            f"sha256={report.trailer_sha256}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", nargs="+", type=Path)
    parser.add_argument(
        "--cpu", choices=("auto", "muc", "dsp", "auc"), default="auto"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    reports: list[FirmwareReport] = []
    failed = False
    for path in args.firmware:
        try:
            cpu: Cpu = infer_cpu(path.name) if args.cpu == "auto" else args.cpu
            reports.append(
                inspect_firmware(path.read_bytes(), source=str(path), cpu=cpu)
            )
        except (OSError, FirmwareFormatError) as exc:
            failed = True
            print(f"ERROR {path}: {exc}", file=sys.stderr)
    if args.json:
        print(json.dumps([asdict(report) for report in reports], indent=2))
    else:
        for report in reports:
            print(_human_report(report))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
