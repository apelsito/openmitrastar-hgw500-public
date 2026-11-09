#!/usr/bin/env python3
"""Build a deterministic, offline evidence oracle for the OEM radar module.

The preserved radar.ko is an analysis input only. This tool never executes,
loads, copies, or redistributes it. When faithful ARC700 execution cannot be
proved, the generated oracle remains explicitly fail-closed and emits only
derived ELF, relocation, CFG, constant, and synthetic-vector evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection


SCHEMA_PREFIX = "openmitrastar.f315-oem-radar-oracle"
EXPECTED_RADAR_SHA256 = "3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332"
EXPECTED_RADAR_BYTES = 109112
DEFAULT_F303_REL = Path("outputs/kernel-port/f303-oem-radar-re-20260904")
DEFAULT_RADAR_RELS = (
    Path("work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/radar/radar.ko"),
    Path("outputs/kernel-port/mtd4-analysis/rootfs/lib/modules/2.6.35.12/extra/radar/radar.ko"),
)
DEFAULT_OUTPUT_REL = Path("outputs/kernel-port/f315-oem-radar-oracle-20260905")

KEY_FUNCTIONS = (
    "radar_preprocess",
    "radar_poll_work",
    "detect_radar_poll",
    "isit_itlv",
    "detect_radar",
    "verify_burst",
    "are_zcs_linear",
    "lsr_detect_poll",
    "lsr_detect_init",
    "lsr_detect_reset",
    "lsr_detect",
)

MMIO_EVIDENCE = {
    "QT4_RADAR_CNT_L": 0xE6091518,
    "QT4_RADAR_PTR_L": 0xE609151C,
    "QT4_RADAR_PTR_H": 0xE6091520,
    "QT4_RADAR_INT_EN": 0xE6091524,
    "QT4_RADAR_CUR_CHMEM_ADR": 0xE6091530,
    "QT4_RADAR_NEW_MODE_START_PTR": 0xE609156C,
    "QT4_RADAR_NEW_MODE_MEM_L_PTR": 0xE6091570,
    "QT4_RADAR_ZC_RAM_BASE": 0xE6400000,
    "QT4_RADAR_MEM_L": 0xE6401000,
    "QT4_RADAR_MEM_H": 0xE6401400,
}

CLASSIFIER_NAMES = (
    "radar_preprocess",
    "make_pulse_town",
    "find_center_pulse",
    "is_it_fh_radar",
    "check_for_fh_radar",
    "check_eu_weather_ocac",
    "isit_itlv",
    "verify_burst",
    "verify_chirp",
    "are_zcs_linear",
    "is_it_tone",
    "lsr_detect",
)

PURE_IMPORTS = {
    "memcpy",
    "memset",
    "strcmp",
    "strncmp",
    "sprintf",
    "snprintf",
    "sscanf",
    "__udivsi3",
    "__umodsi3",
    "__divsi3",
    "__modsi3",
}
LOG_IMPORTS = {"printk", "g_dbg_log_func", "g_dbg_log_module", "g_dbg_log_level"}
TIME_IMPORTS = {
    "do_gettimeofday",
    "schedule",
    "schedule_delayed_work",
    "boot_tvec_bases",
    "mod_timer",
    "init_timer_key",
    "del_timer",
    "jiffies",
}
PLATFORM_IMPORTS = {"bootcfg_get_var", "soc_shared_params"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def align_up(value: int, alignment: int) -> int:
    alignment = max(1, alignment)
    return (value + alignment - 1) & ~(alignment - 1)


def relative_display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def resolve_input(root: Path, explicit: Path | None, candidates: Iterable[Path]) -> Path:
    paths = [explicit] if explicit is not None else [root / candidate for candidate in candidates]
    for path in paths:
        if path is not None and path.is_file():
            return path.resolve()
    rendered = ", ".join(str(path) for path in paths if path is not None)
    raise FileNotFoundError(f"required input not found: {rendered}")


def verify_oem_input(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    digest = sha256_file(path)
    if size != EXPECTED_RADAR_BYTES or digest != EXPECTED_RADAR_SHA256:
        raise ValueError(
            "radar.ko provenance mismatch: "
            f"bytes={size} sha256={digest}; refusing to derive evidence"
        )
    return {"bytes": size, "sha256": digest}


def parse_elf(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        elf = ELFFile(handle)
        sections: list[dict[str, Any]] = []
        load_cursor = 0x10000000
        for index, section in enumerate(elf.iter_sections()):
            flags = int(section["sh_flags"])
            record: dict[str, Any] = {
                "index": index,
                "name": section.name,
                "type": str(section["sh_type"]),
                "flags": flags,
                "size": int(section["sh_size"]),
                "alignment": int(section["sh_addralign"]),
                "file_offset": int(section["sh_offset"]),
                "alloc": bool(flags & 0x2),
                "write": bool(flags & 0x1),
                "execute": bool(flags & 0x4),
            }
            if record["alloc"]:
                load_cursor = align_up(load_cursor, max(4, record["alignment"]))
                record["proposed_address"] = load_cursor
                record["proposed_end"] = load_cursor + record["size"]
                if section["sh_type"] == "SHT_NOBITS":
                    record["initialization"] = "zero-fill"
                    record["content_sha256"] = None
                else:
                    data = section.data()
                    record["initialization"] = "copy-from-input"
                    record["content_sha256"] = sha256_bytes(data)
                load_cursor = record["proposed_end"]
            sections.append(record)

        symtab = elf.get_section_by_name(".symtab")
        if symtab is None:
            raise ValueError("radar.ko has no .symtab")
        symbols: list[dict[str, Any]] = []
        imports: list[str] = []
        for index, symbol in enumerate(symtab.iter_symbols()):
            entry = symbol.entry
            section_index = entry["st_shndx"]
            record = {
                "index": index,
                "name": symbol.name,
                "value": int(entry["st_value"]),
                "size": int(entry["st_size"]),
                "bind": str(entry["st_info"]["bind"]),
                "type": str(entry["st_info"]["type"]),
                "section_index": section_index,
            }
            symbols.append(record)
            if section_index == "SHN_UNDEF" and symbol.name:
                imports.append(symbol.name)

        relocations: list[dict[str, Any]] = []
        relocation_counts: Counter[str] = Counter()
        for relocation_section in elf.iter_sections():
            if not isinstance(relocation_section, RelocationSection):
                continue
            linked_symtab = elf.get_section(relocation_section["sh_link"])
            target_section = elf.get_section(relocation_section["sh_info"])
            for relocation in relocation_section.iter_relocations():
                symbol = linked_symtab.get_symbol(relocation["r_info_sym"])
                type_id = int(relocation["r_info_type"])
                relocation_counts[str(type_id)] += 1
                relocations.append(
                    {
                        "relocation_section": relocation_section.name,
                        "target_section": target_section.name,
                        "offset": int(relocation["r_offset"]),
                        "type_id": type_id,
                        "symbol_index": int(relocation["r_info_sym"]),
                        "symbol": symbol.name,
                        "symbol_section_index": symbol.entry["st_shndx"],
                        "symbol_value": int(symbol.entry["st_value"]),
                        "addend": int(relocation.entry.get("r_addend", 0)),
                    }
                )

        modinfo_section = elf.get_section_by_name(".modinfo")
        modinfo = []
        if modinfo_section is not None:
            modinfo = [
                item.decode("ascii", errors="replace")
                for item in modinfo_section.data().split(b"\0")
                if item
            ]

        return {
            "header": {
                "class": str(elf.header["e_ident"]["EI_CLASS"]),
                "endianness": str(elf.header["e_ident"]["EI_DATA"]),
                "type": str(elf.header["e_type"]),
                "machine": str(elf.header["e_machine"]),
                "entry": int(elf.header["e_entry"]),
                "flags": int(elf.header["e_flags"]),
                "section_count": int(elf.header["e_shnum"]),
            },
            "sections": sections,
            "symbols": symbols,
            "imports": sorted(set(imports)),
            "relocations": relocations,
            "relocation_type_counts": dict(sorted(relocation_counts.items())),
            "modinfo": modinfo,
        }


def parse_function_map(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("empty F303 function map")
    headings = lines[0].split("\t")
    for line in lines[1:]:
        if not line.strip():
            continue
        values = line.split("\t")
        row = dict(zip(headings, values, strict=False))
        address_text = row.get("address", "")
        if not re.fullmatch(r"0x[0-9a-fA-F]+", address_text):
            continue
        length_match = re.match(r"(\d+)", row.get("length", ""))
        records.append(
            {
                "name": row["function"],
                "address": int(address_text, 16),
                "length": int(length_match.group(1)) if length_match else None,
                "confidence": row.get("confidence", "unknown"),
                "role": row.get("role", ""),
                "evidence": row.get("evidence", ""),
            }
        )
    return records


INSTRUCTION_RE = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+(?:[0-9a-fA-F]{4}(?:\s+[0-9a-fA-F]{4})*\s+)"
    r"([a-zA-Z][a-zA-Z0-9_.]*)(?:\s+(.*?))?\s*$"
)
TARGET_RE = re.compile(r";\s*([0-9a-fA-F]+)\s+<([^>]+)>")
IMMEDIATE_RE = re.compile(r"(?<![A-Za-z0-9_])0x([0-9a-fA-F]+)")


def parse_disassembly(path: Path) -> list[dict[str, Any]]:
    instructions: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = INSTRUCTION_RE.match(line)
        if not match or "R_ARC_" in line:
            continue
        target_match = TARGET_RE.search(line)
        instructions.append(
            {
                "address": int(match.group(1), 16),
                "mnemonic": match.group(2),
                "operands": (match.group(3) or "").strip(),
                "direct_target": int(target_match.group(1), 16) if target_match else None,
                "target_label": target_match.group(2) if target_match else None,
            }
        )
    return instructions


def build_cfg_skeleton(
    functions: list[dict[str, Any]],
    instructions: list[dict[str, Any]],
    relocations: list[dict[str, Any]],
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    for function in functions:
        if function["name"] not in KEY_FUNCTIONS or function["length"] is None:
            continue
        start = function["address"]
        end = start + function["length"]
        body = [item for item in instructions if start <= item["address"] < end]
        branches = []
        indirect_calls = []
        immediates: Counter[int] = Counter()
        for instruction in body:
            mnemonic = instruction["mnemonic"].lower()
            for value in IMMEDIATE_RE.findall(instruction["operands"]):
                immediates[int(value, 16)] += 1
            if mnemonic.startswith("b") or mnemonic in {"dbnz", "loop"}:
                branches.append(
                    {
                        "from": instruction["address"],
                        "mnemonic": instruction["mnemonic"],
                        "to": instruction["direct_target"],
                        "label": instruction["target_label"],
                    }
                )
            if mnemonic.startswith("jl") or mnemonic.startswith("bl"):
                indirect_calls.append(
                    {
                        "address": instruction["address"],
                        "mnemonic": instruction["mnemonic"],
                        "operands": instruction["operands"],
                    }
                )
        refs = []
        for relocation in relocations:
            if relocation["target_section"] == ".text" and start <= relocation["offset"] < end:
                refs.append(
                    {
                        "offset": relocation["offset"],
                        "type_id": relocation["type_id"],
                        "symbol": relocation["symbol"],
                        "addend": relocation["addend"],
                    }
                )
        selected.append(
            {
                **function,
                "instruction_count": len(body),
                "direct_branch_count": len(branches),
                "direct_branches": branches,
                "call_instruction_count": len(indirect_calls),
                "call_instructions": indirect_calls,
                "relocation_references": refs,
                "unclassified_immediates": [
                    {"value": value, "hex": f"0x{value:x}", "occurrences": count}
                    for value, count in sorted(immediates.items())
                ],
            }
        )
    return {
        "schema": f"{SCHEMA_PREFIX}.cfg-skeleton/v1",
        "semantics": "structural-only",
        "warning": "Branches and relocation references are not classifier equivalence.",
        "functions": selected,
    }


def classify_import(name: str) -> tuple[str, str]:
    if name in PURE_IMPORTS:
        return "deterministic-library", "implement exact 32-bit ABI behavior in the future harness"
    if name in LOG_IMPORTS:
        return "captured-logging", "capture arguments without host side effects"
    if name in TIME_IMPORTS:
        return "virtual-time", "requires deterministic clock, timers, and work queue"
    if name in PLATFORM_IMPORTS:
        return "fixture-required", "must be supplied explicitly; no guessed default"
    return "kernel-facade", "requires an audited Linux 2.6 ABI facade"


def build_import_stubs(imports: list[str]) -> dict[str, Any]:
    stubs = []
    for index, name in enumerate(imports):
        category, policy = classify_import(name)
        stubs.append(
            {
                "symbol": name,
                "proposed_stub_address": 0x20000000 + index * 0x10,
                "category": category,
                "policy": policy,
                "implemented": False,
            }
        )
    return {
        "schema": f"{SCHEMA_PREFIX}.import-stubs/v1",
        "abi": "ARC700 legacy kernel-module ABI",
        "stub_count": len(stubs),
        "all_stubs_implemented": False,
        "relocation_application": "NOT_IMPLEMENTED",
        "stubs": stubs,
    }


def audit_emulation(root: Path, elf: dict[str, Any], stubs: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    discovered = shutil.which("qemu-system-arc")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(root / "work/qemu-arc-2022.09-build-audit/arc-softmmu/qemu-system-arc")
    seen: set[str] = set()
    qemu = []
    for candidate in candidates:
        try:
            stat = candidate.stat()
            exists = candidate.is_file()
            size = stat.st_size if exists else 0
            executable = bool(exists and os.access(candidate, os.X_OK))
            access_error = None
            key = str(candidate.resolve())
        except OSError as error:
            exists = False
            size = 0
            executable = False
            access_error = {
                "type": type(error).__name__,
                "winerror": getattr(error, "winerror", None),
                "errno": getattr(error, "errno", None),
            }
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        qemu.append(
            {
                "path": relative_display(candidate, root),
                "exists": exists,
                "bytes": size,
                "host_executable": executable,
                "access_error": access_error,
            }
        )

    capstone_spec = importlib.util.find_spec("capstone")
    capstone_arc = False
    if capstone_spec is not None:
        import capstone

        capstone_arc = hasattr(capstone, "CS_ARCH_ARC")
    unicorn_spec = importlib.util.find_spec("unicorn")
    unicorn_arc = False
    if unicorn_spec is not None:
        import unicorn

        unicorn_arc = hasattr(unicorn, "UC_ARCH_ARC")

    blockers = []
    if elf["header"]["type"] != "ET_EXEC":
        blockers.append("OEM input is ET_REL kernel-module code, not an executable image")
    if elf["header"]["entry"] == 0:
        blockers.append("OEM input has no executable entrypoint")
    if elf["relocations"]:
        blockers.append(f"{len(elf['relocations'])} ARC relocations are not yet applied")
    if not stubs["all_stubs_implemented"]:
        blockers.append(f"{stubs['stub_count']} Linux 2.6/kernel/platform imports lack audited stubs")
    if not capstone_arc:
        blockers.append("installed Capstone has no ARC decoder")
    if not unicorn_arc:
        blockers.append("installed Unicorn has no ARC execution backend")
    if not any(item["exists"] and item["bytes"] > 0 and item["host_executable"] for item in qemu):
        blockers.append("no non-empty executable qemu-system-arc is visible to this host process")
    blockers.append("no deterministic Linux 2.6 module loader/kernel-state harness exists")

    return {
        "schema": f"{SCHEMA_PREFIX}.emulation-audit/v1",
        "requested_architecture": "ARC700 little-endian legacy ABI",
        "full_oem_execution": "NOT_VIABLE",
        "classifier_equivalence": "NOT_PROVEN",
        "mode_selected": "STATIC_ORACLE_FAIL_CLOSED",
        "capstone_available": capstone_spec is not None,
        "capstone_arc_backend": capstone_arc,
        "unicorn_available": unicorn_spec is not None,
        "unicorn_arc_backend": unicorn_arc,
        "qemu_candidates": qemu,
        "blockers": blockers,
    }


def extract_constants(disassembly_path: Path, strings_path: Path) -> dict[str, Any]:
    disassembly = disassembly_path.read_text(encoding="utf-8", errors="replace").lower()
    strings = strings_path.read_text(encoding="utf-8", errors="replace")
    mmio = []
    for name, address in MMIO_EVIDENCE.items():
        rendered = f"{address:08x}"
        objdump_rendered = f"{rendered[:4]} {rendered[4:]}"
        mmio.append(
            {
                "name": name,
                "address": address,
                "hex": f"0x{address:08x}",
                "disassembly_occurrences": disassembly.count(objdump_rendered),
            }
        )
    names = [
        {"name": name, "present": name in strings, "semantic_status": "name-only-evidence"}
        for name in CLASSIFIER_NAMES
    ]
    return {
        "schema": f"{SCHEMA_PREFIX}.constants/v1",
        "mmio": mmio,
        "classifier_names": names,
        "acquisition_constants": {
            "pulse_timestamp_mask": 0x07FFFFFF,
            "pulse_fifo_depth": 256,
            "zero_crossing_rows_per_poll_max": 18,
            "zero_crossing_words_per_pulse": 28,
            "zero_crossing_samples_per_pulse": 112,
        },
        "classifier_threshold_semantics": "NOT_RECOVERED",
    }


def build_vector_corpus(f303_dir: Path) -> dict[str, Any]:
    vectors = []
    vector_dir = f303_dir / "test-vectors"
    for path in sorted(vector_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != "openmitrastar.f303-radar-vector/v1":
            continue
        if payload.get("source") != "synthetic":
            continue
        vector_bytes = stable_json(payload).encode("ascii")
        vectors.append(
            {
                "name": payload.get("name", path.stem),
                "source": "synthetic",
                "input_sha256": sha256_bytes(vector_bytes),
                "region": payload.get("region", "unknown"),
                "channel": payload.get("channel"),
                "bandwidth_mhz": payload.get("bandwidth_mhz"),
                "pulse_pair_count": len(payload.get("fifo", {}).get("mem_h_words", [])),
                "expected": payload.get("expected", {}),
                "classifier_result_origin": "explicit-vector-oracle-fields",
            }
        )
    return {
        "schema": f"{SCHEMA_PREFIX}.vector-corpus/v1",
        "vector_count": len(vectors),
        "vectors": vectors,
        "contains_oem_binary": False,
        "contains_physical_capture": False,
        "classification_algorithm": "NOT_IMPLEMENTED",
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(stable_json(payload), encoding="ascii")


def generate(root: Path, radar_path: Path, f303_dir: Path, output_dir: Path) -> dict[str, Any]:
    provenance = verify_oem_input(radar_path)
    required_f303 = (
        "elf-sections.txt",
        "elf-relocations.txt",
        "elf-symbols.txt",
        "function-map.tsv",
        "objdump-dr.txt",
        "strings-offsets.txt",
        "manifest.json",
    )
    missing = [name for name in required_f303 if not (f303_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing F303 evidence: {', '.join(missing)}")

    elf = parse_elf(radar_path)
    function_map = parse_function_map(f303_dir / "function-map.tsv")
    instructions = parse_disassembly(f303_dir / "objdump-dr.txt")
    stubs = build_import_stubs(elf["imports"])
    emulation = audit_emulation(root, elf, stubs)
    cfg = build_cfg_skeleton(function_map, instructions, elf["relocations"])
    constants = extract_constants(
        f303_dir / "objdump-dr.txt", f303_dir / "strings-offsets.txt"
    )
    vectors = build_vector_corpus(f303_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    load_map = {
        "schema": f"{SCHEMA_PREFIX}.elf-load-map/v1",
        "input_type": elf["header"]["type"],
        "base_address": 0x10000000,
        "sections": [section for section in elf["sections"] if section["alloc"]],
        "applied_to_binary": False,
    }
    relocation_map = {
        "schema": f"{SCHEMA_PREFIX}.relocations/v1",
        "count": len(elf["relocations"]),
        "type_counts": elf["relocation_type_counts"],
        "application_status": "NOT_IMPLEMENTED",
        "entries": elf["relocations"],
    }
    input_records = {
        "radar_ko": {
            "path": relative_display(radar_path, root),
            **provenance,
            "role": "private-analysis-input-only",
            "copied_to_output": False,
            "runtime_dependency": False,
            "redistributable_payload": False,
        },
        "f303": {
            name: {
                "path": relative_display(f303_dir / name, root),
                "bytes": (f303_dir / name).stat().st_size,
                "sha256": sha256_file(f303_dir / name),
            }
            for name in required_f303
        },
    }
    provenance_doc = {
        "schema": f"{SCHEMA_PREFIX}.provenance/v1",
        "target": "OpenMitraStar HGW-500BNA-QCv2 A2",
        "inputs": input_records,
        "outputs_are_derived_metadata_only": True,
        "oem_runtime_retained": False,
        "oem_binary_embedded": False,
        "hardware_used": False,
        "router_contacted": False,
    }
    audit = {
        "schema": f"{SCHEMA_PREFIX}.audit/v1",
        "status": "PASS_STATIC_ORACLE_FAIL_CLOSED",
        "execution": emulation,
        "elf": {
            "header": elf["header"],
            "modinfo": elf["modinfo"],
            "alloc_section_count": sum(1 for item in elf["sections"] if item["alloc"]),
            "symbol_count": len(elf["symbols"]),
            "import_count": len(elf["imports"]),
            "relocation_count": len(elf["relocations"]),
        },
        "extraction": {
            "load_map": "PASS",
            "relocations": "PASS_UNAPPLIED",
            "import_stub_plan": "PASS_UNIMPLEMENTED",
            "cfg_skeleton": "PASS_STRUCTURAL_ONLY",
            "constants": "PASS_WITHOUT_SEMANTIC_EQUIVALENCE",
            "synthetic_vectors": "PASS",
        },
        "claims": {
            "oem_classifier_executed": False,
            "source_equivalence": False,
            "dfs_detection_proven": False,
            "safe_for_runtime_integration": False,
        },
        "safety": {
            "network": False,
            "ssh": False,
            "uart": False,
            "com": False,
            "tftp": False,
            "module_load": False,
            "mmio": False,
            "radio_mutation": False,
            "flash": False,
            "mtd": False,
        },
        "next_gate": (
            "Implement ARC relocation semantics plus every required deterministic stub, "
            "then prove instruction-level execution against fixed vectors before changing status."
        ),
    }

    documents = {
        "oracle-audit.json": audit,
        "provenance.json": provenance_doc,
        "elf-load-map.json": load_map,
        "relocation-map.json": relocation_map,
        "import-stubs.json": stubs,
        "cfg-skeleton.json": cfg,
        "constants.json": constants,
        "vector-corpus.json": vectors,
    }
    for name, payload in documents.items():
        write_json(output_dir / name, payload)

    readme = (
        "OpenMitraStar F315 OEM radar offline oracle\n"
        "\n"
        "Status: PASS_STATIC_ORACLE_FAIL_CLOSED\n"
        "The OEM radar.ko was hashed and parsed as private analysis input only.\n"
        "It is not copied, executed, loaded, redistributed, or required at runtime.\n"
        "The output proves ELF/load-map/relocation/import/CFG extraction only.\n"
        "OEM classifier execution and equivalence remain NOT PROVEN.\n"
        "No router, network, UART, COM, TFTP, MMIO, radio, flash, or MTD was used.\n"
    )
    (output_dir / "README.txt").write_text(readme, encoding="ascii")

    primary_files = sorted(path for path in output_dir.iterdir() if path.is_file())
    manifest = {
        "schema": f"{SCHEMA_PREFIX}.manifest/v1",
        "status": audit["status"],
        "files": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in primary_files
        ],
    }
    write_json(output_dir / "manifest.json", manifest)
    sum_files = sorted(path for path in output_dir.iterdir() if path.name != "SHA256SUMS")
    sums = "".join(f"{sha256_file(path)}  {path.name}\n" for path in sum_files)
    (output_dir / "SHA256SUMS").write_text(sums, encoding="ascii")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--radar-ko", type=Path)
    parser.add_argument("--f303-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--require-execution",
        action="store_true",
        help="exit nonzero unless faithful OEM execution is viable",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    radar_path = resolve_input(root, args.radar_ko, DEFAULT_RADAR_RELS)
    f303_dir = (args.f303_dir or root / DEFAULT_F303_REL).resolve()
    output_dir = (args.output_dir or root / DEFAULT_OUTPUT_REL).resolve()
    audit = generate(root, radar_path, f303_dir, output_dir)
    summary = {
        "status": audit["status"],
        "execution": audit["execution"]["full_oem_execution"],
        "classifier_equivalence": audit["execution"]["classifier_equivalence"],
        "output": relative_display(output_dir, root),
    }
    print(json.dumps(summary, sort_keys=True))
    if args.require_execution and audit["execution"]["full_oem_execution"] != "VIABLE":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
