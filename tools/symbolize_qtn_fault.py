#!/usr/bin/env python3
"""Symbolize Quantenna ARC fault addresses from a captured module map.

This is an offline helper.  It does not connect to the router and it does not
modify hardware state.  The expected module map is the output captured by
run_qtn_w3_tx7_client_traffic.py between OMW3TX7_MODULE_MAP_BEGIN/END.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NM = ROOT / "tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/llvm-nm.exe"
DEFAULT_MODULES = {
    "qdrv": ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv.ko",
    "wlan": ROOT / "work/linux510-radio-port/quantenna/wlan/wlan.ko",
    "hbm": ROOT / "work/linux510-radio-port/quantenna/platform/topaz/hbm.ko",
    "switch_tqe": ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.ko",
    "switch_emac": ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_emac.ko",
    "topaz_congest_queue": ROOT / "work/linux510-radio-port/quantenna/platform/topaz/topaz_congest_queue.ko",
    "fwt_if": ROOT / "work/linux510-radio-port/quantenna/platform/topaz/fwt_if.ko",
    "dmautil": ROOT / "work/linux510-radio-port/quantenna/platform/ruby/dmautil.ko",
    "iputil": ROOT / "work/linux510-radio-port/quantenna/platform/ruby/iputil.ko",
    "runtime_compat": ROOT / "work/linux510-radio-port/quantenna/platform/ruby/runtime_compat.ko",
    "board_compat": ROOT / "work/linux510-radio-port/quantenna/platform/ruby/board_compat.ko",
    "qtn_platform_support": ROOT / "work/linux510-radio-port/quantenna/platform/ruby/qtn_platform_support.ko",
    "qtn_pm_qos_compat": ROOT / "work/linux510-radio-port/quantenna/platform/ruby/qtn_pm_qos_compat.ko",
}

HEX_RE = r"0x[0-9a-fA-F]+"
MODULE_TEXT_RE = re.compile(r"^(?P<name>[A-Za-z0-9_]+)=(?P<value>0x[0-9a-fA-F]+|missing)$")
PROC_MODULE_RE = re.compile(r"^(?P<name>[A-Za-z0-9_]+)\s+(?P<size>\d+)\s+")


def parse_int(value: str) -> int:
    return int(value, 16 if value.lower().startswith("0x") else 10)


def parse_fault_addresses(text: str) -> dict[str, int]:
    addresses: dict[str, int] = {}
    patterns = {
        "workqueue": rf"Workqueue:\s+\S+\s+(?P<addr>{HEX_RE})",
        "efa": rf"\bEFA:\s+(?P<addr>{HEX_RE})",
        "eret": rf"\bERET:\s+(?P<addr>{HEX_RE})",
        "blk": rf"\bBLK:\s+(?P<addr>{HEX_RE})",
        "bta": rf"\bBTA:\s+(?P<addr>{HEX_RE})",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            addresses[name] = parse_int(match.group("addr"))
    reg_match = re.search(r"\br01:\s+(?P<addr>0x[0-9a-fA-F]+)", text)
    if reg_match:
        addresses["r01"] = parse_int(reg_match.group("addr"))
    if "efa" in addresses and "r01" in addresses:
        addresses["efa_minus_r01"] = addresses["efa"] - addresses["r01"]
    return addresses


def parse_module_map(text: str) -> dict[str, dict[str, int]]:
    modules: dict[str, dict[str, int]] = {}
    in_map = "OMW3TX7_MODULE_MAP_BEGIN" not in text
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "OMW3TX7_MODULE_MAP_BEGIN":
            in_map = True
            continue
        if line == "OMW3TX7_MODULE_MAP_END":
            break
        if not in_map:
            continue
        text_match = MODULE_TEXT_RE.match(line)
        if text_match:
            name = text_match.group("name")
            value = text_match.group("value")
            entry = modules.setdefault(name, {})
            if value == "missing":
                entry["missing_text_base"] = 1
            else:
                entry["text_base"] = parse_int(value)
            continue
        proc_match = PROC_MODULE_RE.match(line)
        if proc_match:
            name = proc_match.group("name")
            modules.setdefault(name, {})["module_size"] = int(proc_match.group("size"))
    return modules


def load_symbols(module: Path, nm: Path) -> list[tuple[int, str]]:
    if not module.is_file() or not nm.is_file():
        return []
    result = subprocess.run(
        [str(nm), "-n", "--defined-only", str(module)],
        cwd=ROOT, text=True, capture_output=True, timeout=20, check=True,
    )
    symbols: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        match = re.match(r"^([0-9a-fA-F]+)\s+\S\s+(.+)$", line.strip())
        if not match:
            continue
        symbols.append((int(match.group(1), 16), match.group(2)))
    symbols.sort()
    return symbols


def nearest_symbol(symbols: list[tuple[int, str]], offset: int) -> dict[str, object] | None:
    best: tuple[int, str] | None = None
    for value, name in symbols:
        if value > offset:
            break
        best = (value, name)
    if best is None:
        return None
    return {"name": best[1], "offset": best[0], "delta": offset - best[0]}


def resolve_addresses(
    addresses: dict[str, int],
    modules: dict[str, dict[str, int]],
    module_paths: dict[str, Path],
    nm: Path,
) -> list[dict[str, object]]:
    symbol_cache: dict[str, list[tuple[int, str]]] = {}
    rows: list[dict[str, object]] = []
    for address_name in ("workqueue", "eret", "blk", "bta"):
        address = addresses.get(address_name)
        if address is None:
            continue
        candidates: list[dict[str, object]] = []
        for module_name, data in sorted(modules.items()):
            base = data.get("text_base")
            if base is None or address < base:
                continue
            offset = address - base
            size = data.get("module_size")
            if size is not None and offset >= size:
                continue
            if module_name not in symbol_cache:
                symbol_cache[module_name] = load_symbols(
                    module_paths.get(module_name, Path()), nm
                )
            symbol = nearest_symbol(symbol_cache[module_name], offset)
            candidates.append({
                "module": module_name,
                "address": f"0x{address:08x}",
                "offset": f"0x{offset:x}",
                "module_size": size,
                "nearest_symbol": symbol,
            })
        rows.append({
            "address_name": address_name,
            "address": f"0x{address:08x}",
            "candidates": candidates,
        })
    if "efa_minus_r01" in addresses:
        rows.append({
            "address_name": "efa_minus_r01",
            "address": addresses["efa_minus_r01"],
            "interpretation": "EFA-r01 byte offset; 0x18 is the 802.11 management body after the 24-byte header",
        })
    return rows


def render_text(rows: Iterable[dict[str, object]]) -> str:
    lines: list[str] = []
    for row in rows:
        if row["address_name"] == "efa_minus_r01":
            lines.append(f"efa_minus_r01={row['address']} {row['interpretation']}")
            continue
        lines.append(f"{row['address_name']} {row['address']}")
        candidates = row.get("candidates", [])
        if not candidates:
            lines.append("  unresolved: no captured module text base covers this address")
            continue
        for candidate in candidates:  # type: ignore[assignment]
            symbol = candidate.get("nearest_symbol")
            if symbol:
                sym = f"{symbol['name']}+0x{symbol['delta']:x}"  # type: ignore[index]
            else:
                sym = "no local symbol"
            lines.append(f"  {candidate['module']} offset={candidate['offset']} {sym}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault-log", type=Path, required=True)
    parser.add_argument("--module-map", type=Path, required=True)
    parser.add_argument("--nm", type=Path, default=DEFAULT_NM)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    addresses = parse_fault_addresses(args.fault_log.read_text(encoding="utf-8", errors="replace"))
    modules = parse_module_map(args.module_map.read_text(encoding="utf-8", errors="replace"))
    rows = resolve_addresses(addresses, modules, DEFAULT_MODULES, args.nm)
    payload = {
        "schema": "openmitrastar.qtn-fault-symbolization/v1",
        "fault_log": str(args.fault_log),
        "module_map": str(args.module_map),
        "addresses": {key: (f"0x{value:08x}" if key != "efa_minus_r01" else value)
                      for key, value in addresses.items()},
        "modules_with_text_base": sorted(
            name for name, data in modules.items() if "text_base" in data
        ),
        "resolved": rows,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_text(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
