"""Recover ARC ET_REL operation metadata without hardware or binary data export.

The output is an exhaustive relocation/symbol inventory of the supplied modules,
plus lexical callback assignments from explicitly selected source directories.
It is not a decompiler, CFG proof, source-equivalence gate, or firmware release.
Only metadata is exported: no strings, calibration, keys, raw sections or images.
Python standard library only; supplied inputs are read twice to detect changes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parents[1]
F365 = ROOT / "outputs/rea/arc700-20261021-r2/f365-ram-activation/r3/payload/modules"
OEM = ROOT / "work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra"
DEFAULT_MODULES = {
    "oem_qdrv": OEM / "qdrv/qdrv.ko",
    "oem_wlan": OEM / "wlan/wlan.ko",
    "oem_switch_tqe": OEM / "topaz/switch_tqe.ko",
    "f365_qdrv": F365 / "qdrv.ko",
    "f365_wlan": F365 / "wlan.ko",
    "active_lineage_switch_tqe": ROOT / "outputs/rea/arc700-20261021-r2/tqe-current/switch_tqe.ko",
    "f370_qdrv": ROOT / "outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/a/qdrv.ko",
}
DEFAULT_SOURCES = {
    "f364_qdrv": ROOT / "work/linux510-radio-port/quantenna-f364-lifetime/qdrv",
    "port_wlan": ROOT / "work/linux510-radio-port/quantenna/wlan",
    "oem_qdrv_gpl": ROOT / "work/sources/Quantenna-GPL/drivers/qdrv",
    "oem_wlan_gpl": ROOT / "work/sources/Quantenna-GPL/drivers/wlan",
    "net80211_abi": ROOT / "work/sources/Quantenna-GPL/drivers/include/kernel/net80211",
    "port_tqe": ROOT / "work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_tqe.c",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def safe_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_.$][A-Za-z0-9_.$]*", value))


class Elf:
    """Bounded ELF32LE parser; export only structural metadata."""

    def __init__(self, path: Path):
        self.path = path
        self.raw = path.read_bytes()
        if self.raw[:6] != b"\x7fELF\x01\x01" or len(self.raw) < 52:
            raise ValueError(f"{path}: expected ELF32 little-endian")
        if struct.unpack_from("<HH", self.raw, 16) != (1, 93):
            raise ValueError(f"{path}: expected ET_REL EM_ARC_COMPACT=93")
        off = struct.unpack_from("<I", self.raw, 32)[0]
        width, count, names_index = struct.unpack_from("<HHH", self.raw, 46)
        if width != 40 or not count or names_index >= count or off + count * width > len(self.raw):
            raise ValueError("invalid section table")
        headers = [struct.unpack_from("<10I", self.raw, off + i * width) for i in range(count)]
        self.sections = []
        names = self._span(headers[names_index][4], headers[names_index][5])
        for index, h in enumerate(headers):
            payload = b"" if h[1] == 8 else self._span(h[4], h[5])
            self.sections.append(dict(index=index, name=self._cstring(names, h[0]),
                                      type=h[1], flags=h[2], size=h[5], link=h[6],
                                      info=h[7], align=h[8], entsize=h[9], data=payload))
        self.byname = {s["name"]: s for s in self.sections}
        self.syms = []
        symbol_tables = [s for s in self.sections if s["type"] == 2]
        if len(symbol_tables) != 1:
            raise ValueError("expected exactly one symbol table")
        table = symbol_tables[0]
        if table["entsize"] != 16 or table["size"] % 16 or table["link"] >= count:
            raise ValueError("invalid symbol table")
        strings = self.sections[table["link"]]["data"]
        for cursor in range(0, table["size"], 16):
            name, value, length, info, other, section = struct.unpack_from("<IIIBBH", table["data"], cursor)
            self.syms.append(dict(index=len(self.syms), name=self._cstring(strings, name), value=value,
                                  size=length, type=info & 15, bind=info >> 4, other=other, section=section))
        self.relocs = []
        for sec in self.sections:
            if sec["type"] not in (4, 9):
                continue
            size = 12 if sec["type"] == 4 else 8
            if sec["entsize"] != size or sec["size"] % size or sec["link"] != table["index"] or sec["info"] >= count:
                raise ValueError("invalid relocation table")
            for cursor in range(0, sec["size"], size):
                offset, info = struct.unpack_from("<II", sec["data"], cursor)
                symbol = info >> 8
                if symbol >= len(self.syms) or offset >= self.sections[sec["info"]]["size"]:
                    raise ValueError("relocation outside table/target section")
                addend = struct.unpack_from("<i", sec["data"], cursor + 8)[0] if size == 12 else None
                self.relocs.append(dict(section_index=sec["info"], section=self.sections[sec["info"]]["name"],
                                        offset=offset, type=info & 255, symbol=symbol, addend=addend))

    def _span(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.raw):
            raise ValueError("ELF span outside file")
        return self.raw[offset:offset + size]

    @staticmethod
    def _cstring(data: bytes, offset: int) -> str:
        if offset < 0 or offset >= len(data):
            raise ValueError("string offset outside table")
        end = data.find(b"\0", offset)
        if end < 0:
            raise ValueError("unterminated table string")
        return data[offset:end].decode("utf-8", errors="replace")

    def section_name(self, symbol: dict) -> str:
        value = symbol["section"]
        return self.sections[value]["name"] if value < len(self.sections) else f"SPECIAL_{value}"

    def public_symbol(self, symbol: dict) -> dict:
        return {**{k: symbol[k] for k in ("name", "value", "size", "type", "bind")},
                "section": self.section_name(symbol)}

    def containing_object(self, section: int, offset: int) -> dict | None:
        matches = [s for s in self.syms if s["type"] == 1 and s["section"] == section
                   and s["size"] and s["value"] <= offset < s["value"] + s["size"]]
        return min(matches, key=lambda s: (s["size"], s["name"])) if matches else None

    def resolve_function(self, relocation: dict) -> tuple[dict | None, str]:
        symbol = self.syms[relocation["symbol"]]
        if symbol["type"] == 2:
            return symbol, "STT_FUNC"
        if symbol["type"] == 3 and relocation["addend"] is not None:
            target = symbol["value"] + relocation["addend"]
            matches = [s for s in self.syms if s["section"] == symbol["section"]
                       and s["type"] == 2 and s["value"] == target]
            if matches:
                return min(matches, key=lambda s: s["name"]), "SECTION_PLUS_ADDEND_EXACT_FUNCTION_START"
        return None, "UNRESOLVED_FUNCTION_TYPE"

    def inventory(self) -> dict:
        objects = {}
        rows = []
        for r in self.relocs:
            section = self.sections[r["section_index"]]
            if not section["flags"] & 2 or section["flags"] & 4:
                continue
            target = self.syms[r["symbol"]]
            owner = self.containing_object(r["section_index"], r["offset"])
            function, resolution = self.resolve_function(r)
            row = {k: r[k] for k in ("section", "offset", "type", "addend")}
            row.update(target_symbol=target["name"], target_section=self.section_name(target),
                       target_type=target["type"], owner=owner["name"] if owner else None,
                       owner_offset=r["offset"] - owner["value"] if owner else None,
                       function=function["name"] if function else None, resolution=resolution)
            rows.append(row)
            if owner and function:
                objects.setdefault((owner["section"], owner["value"], owner["name"]),
                                   {**self.public_symbol(owner), "callbacks": []})["callbacks"].append(row)
        # Include named ops objects with no pointer relocations, notably mutable
        # vnet_device_ops in BSS. Their assignments are recovered from source.
        for s in self.syms:
            if s["type"] == 1 and re.search(r"(?:ops|handlers|handler_table|command_table)$", s["name"]):
                objects.setdefault((s["section"], s["value"], s["name"]),
                                   {**self.public_symbol(s), "callbacks": []})
        # OEM modules have most local object symbols stripped. Retain explicit
        # anonymous ranges for contiguous function-pointer relocations rather
        # than silently claiming their operations were absent.
        anonymous = []
        for row in rows:
            if row["function"] and row["owner"] is None:
                if (anonymous and anonymous[-1]["section"] == row["section"]
                        and row["offset"] - anonymous[-1]["last_offset"] <= 16):
                    anonymous[-1]["callbacks"].append(row)
                    anonymous[-1]["last_offset"] = row["offset"]
                else:
                    anonymous.append(dict(name="anonymous_" + row["section"] + "_" + hex(row["offset"]),
                                          section=row["section"], value=row["offset"], last_offset=row["offset"],
                                          resolution="ANONYMOUS_RELOCATION_RANGE_NOT_PROVEN_C_OBJECT", callbacks=[row]))
        tables = sorted([*objects.values(), *anonymous], key=lambda x: (x["section"], x["value"], x["name"]))
        funcs = [self.public_symbol(s) for s in self.syms if s["type"] == 2 and s["section"] != 0]
        imports = sorted({s["name"] for s in self.syms if s["section"] == 0 and s["bind"] in (1, 2) and s["name"]})
        exported = self.byname.get("__ksymtab_strings", {}).get("data", b"")
        exports = sorted({x.decode("ascii") for x in exported.split(b"\0") if x and safe_identifier(x.decode("ascii"))})
        unresolved = [r for r in rows if not r["function"] and r["target_type"] not in (1, 3)]
        return dict(path=display_path(self.path), bytes=len(self.raw), sha256=hashlib.sha256(self.raw).hexdigest(),
                    elf="ELF32LE_ET_REL_EM_ARC_COMPACT_93", symbols_total=len(self.syms),
                    symbols=[self.public_symbol(s) for s in self.syms], functions=funcs,
                    imports=imports, exports=exports, relocation_count=len(self.relocs),
                    allocated_data_relocation_count=len(rows),
                    function_pointer_relocation_count=sum(bool(r["function"]) for r in rows),
                    allocated_data_relocations=rows, callback_objects=tables,
                    unresolved_nonobject_data_relocations=unresolved,
                    sections=[{k: s[k] for k in ("index", "name", "type", "flags", "size", "align")} for s in self.sections])

    def ioctl_records(self) -> list[dict]:
        matches = [s for s in self.syms if s["name"] == "ieee80211_priv_args" and s["type"] == 1]
        if not matches:
            # ARC32 OEM iw_handler_def: standard pointer at 0, two u16 counts
            # at 4/6, private_args u16 at 8, private pointer at 12 and args at 16.
            # Identify the complete table through these three relocations and
            # counts; the older name-anchor heuristic found only a suffix.
            relocmap = {(r["section_index"], r["offset"]): r for r in self.relocs}
            inferred = []
            for sec in self.sections:
                if not sec["flags"] & 2 or sec["flags"] & 4 or sec["type"] == 8:
                    continue
                for cursor in range(0, max(0, sec["size"] - 20), 4):
                    standard, private, count = struct.unpack_from("<HHH", sec["data"], cursor + 4)
                    if not 1 <= standard <= 256 or not 1 <= private <= 64 or not 1 <= count <= 2048:
                        continue
                    records = [relocmap.get((sec["index"], cursor + p)) for p in (0, 12, 16)]
                    if not all(records):
                        continue
                    pointers = []
                    for r in records:
                        symbol = self.syms[r["symbol"]]
                        if symbol["section"] >= len(self.sections) or r["addend"] is None:
                            break
                        pointers.append((symbol["section"], symbol["value"] + r["addend"]))
                    if len(pointers) != 3:
                        continue
                    table_section, start = pointers[2]
                    data = self.sections[table_section]["data"]
                    if start < 0 or start + 24 * count > len(data):
                        continue
                    decoded = self._decode_ioctls(data[start:start + 24 * count])
                    if any(r["cmd"] == 0x8BE0 and r["set_args"] == 0x4802 and r["name"] == "setparam" for r in decoded):
                        inferred.append(decoded)
            if len(inferred) != 1:
                raise ValueError("cannot uniquely recover stripped iw_priv_args through handler definition")
            return inferred[0]
        if len(matches) != 1 or matches[0]["size"] % 24:
            raise ValueError("invalid iw_priv_args object")
        symbol = matches[0]
        sec = self.sections[symbol["section"]]
        payload = sec["data"][symbol["value"]:symbol["value"] + symbol["size"]]
        return self._decode_ioctls(payload)

    @staticmethod
    def _decode_ioctls(payload: bytes) -> list[dict]:
        records = []
        for cursor in range(0, len(payload), 24):
            cmd, set_args, get_args = struct.unpack_from("<IHH", payload, cursor)
            raw_name = payload[cursor + 8:cursor + 24]
            try:
                name = raw_name.split(b"\0", 1)[0].decode("ascii")
            except UnicodeDecodeError:
                return []
            if name and not re.fullmatch(r"[A-Za-z0-9_]+", name):
                return []
            records.append(dict(index=cursor // 24, cmd=cmd, set_args=set_args, get_args=get_args, name=name))
        return records

    def wext_definition(self) -> dict | None:
        """Recover both exact pointer arrays through ARC32 iw_handler_def."""
        relocmap = {(r["section_index"], r["offset"]): r for r in self.relocs}
        found = []
        for sec in self.sections:
            if not sec["flags"] & 2 or sec["flags"] & 4 or sec["type"] == 8:
                continue
            for cursor in range(0, max(0, sec["size"] - 20), 4):
                standard, private, count = struct.unpack_from("<HHH", sec["data"], cursor + 4)
                if not 1 <= standard <= 256 or not 1 <= private <= 64 or not 1 <= count <= 2048:
                    continue
                pointers = []
                for offset in (0, 12, 16):
                    r = relocmap.get((sec["index"], cursor + offset))
                    if r is None or r["addend"] is None:
                        break
                    symbol = self.syms[r["symbol"]]
                    if symbol["section"] >= len(self.sections):
                        break
                    pointers.append((symbol["section"], symbol["value"] + r["addend"]))
                if len(pointers) != 3:
                    continue
                index, start = pointers[2]
                payload = self.sections[index]["data"]
                if start < 0 or start + 24 * count > len(payload):
                    continue
                ioctls = self._decode_ioctls(payload[start:start + 24 * count])
                if not any(r["cmd"] == 0x8BE0 and r["set_args"] == 0x4802 and r["name"] == "setparam" for r in ioctls):
                    continue
                arrays = {}
                for name, n, pointer in (("standard", standard, pointers[0]), ("private", private, pointers[1])):
                    index, start = pointer
                    target_sec = self.sections[index]
                    if start < 0 or start + 4 * n > len(target_sec["data"]):
                        raise ValueError("WEXT handler pointer array outside section")
                    rows = []
                    for slot in range(n):
                        offset = start + slot * 4
                        r = relocmap.get((index, offset))
                        if r:
                            f, resolution = self.resolve_function(r)
                            s = self.syms[r["symbol"]]
                            row = dict(index=slot, ioctl=(0x8B00 if name == "standard" else 0x8BE0) + slot,
                                       function=f["name"] if f else None, target_section=self.section_name(s),
                                       target_offset=s["value"] + r["addend"] if r["addend"] is not None else None,
                                       resolution=resolution)
                        else:
                            raw = struct.unpack_from("<I", target_sec["data"], offset)[0]
                            row = dict(index=slot, ioctl=(0x8B00 if name == "standard" else 0x8BE0) + slot,
                                       function=None, resolution="NULL" if raw == 0 else "UNRESOLVED_NONZERO_NO_RELOCATION")
                        rows.append(row)
                    arrays[name] = dict(count=n, section=target_sec["name"], offset=start, slots=rows,
                                        nonnull=sum(x["resolution"] != "NULL" for x in rows),
                                        unnamed=sum(x["function"] is None and x["resolution"] != "NULL" for x in rows))
                found.append(dict(section=sec["name"], offset=cursor, layout="ARC32_OEM_iw_handler_def_standard0_counts4_6_8_private12_args16",
                                  private_args_count=count, arrays=arrays,
                                  evidence="EXACT_COUNTS_POINTER_RELOCATIONS_AND_PRIVATE_ARG_RECORDS"))
        if not found:
            return None
        if len(found) != 1:
            raise ValueError("ambiguous WEXT handler definitions")
        return found[0]


def strip_comments_preserve_lines(text: str) -> str:
    def replace(m: re.Match) -> str:
        return "".join("\n" if c == "\n" else " " for c in m.group())
    # Keep string/character tokens opaque, so comment-looking text inside them
    # does not erase following source or corrupt line evidence.
    pattern = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*'
    return re.sub(pattern, lambda m: replace(m) if m.group().startswith(("/*", "//")) else m.group(), text, flags=re.S)


def mask_strings_preserve_lines(text: str) -> str:
    pattern = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: "".join("\n" if c == "\n" else " " for c in m.group()), text)


def source_inventory(sources: dict[str, Path], known_functions: set[str]) -> tuple[dict, dict[str, str]]:
    files = {}
    for label, location in sources.items():
        if not location.exists():
            raise FileNotFoundError(location)
        selected = [location] if location.is_file() else sorted([*location.glob("*.c"), *location.glob("*.h")])
        for path in selected:
            files.setdefault(path.resolve(), set()).add(label)
    texts = {}
    declarations = []
    declared = set()
    pins = {}
    for path, labels in files.items():
        # Generated .mod.c adds kernel module metadata but no source ops value.
        if path.name.endswith(".mod.c"):
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        text = mask_strings_preserve_lines(strip_comments_preserve_lines(original))
        texts[path] = (labels, text)
        pins[str(path)] = sha(path)
        for m in re.finditer(r"\(\s*\*\s*((?:ic_|iv_)[A-Za-z0-9_]+)\s*\)\s*\(", text):
            declared.add(m[1])
            declarations.append(dict(field=m[1], path=display_path(path), line=text.count("\n", 0, m.start()) + 1))
        known_functions.update(m[1] for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", text)
                               if m[1] not in {"if", "for", "while", "switch"})
    assignments = []
    registrations = []
    source_tables = []
    for path, (labels, text) in texts.items():
        for m in re.finditer(r"(?P<lhs>[A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*|\.[A-Za-z_]\w*)\s*=\s*(?P<rhs>[A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*[;,]", text):
            lhs, rhs = re.sub(r"\s+", "", m["lhs"]), re.sub(r"\s+", "", m["rhs"])
            field = re.split(r"->|\.", lhs)[-1]
            is_field = field in declared or field.startswith("ndo_") or field in {"handler", "notify", "notifier_call", "xmit_func", "rx_func"}
            if is_field or rhs in known_functions:
                assignments.append(dict(path=display_path(path), source_labels=sorted(labels), line=text.count("\n", 0, m.start()) + 1,
                                         lhs=lhs, field=field, rhs=rhs,
                                         evidence="LEXICAL_SOURCE_ASSIGNMENT_NOT_PREPROCESSED", declared_callback=is_field,
                                         target_known_function=rhs in known_functions))
        calls = r"(?:INIT_WORK|INIT_DELAYED_WORK|timer_setup|setup_timer|init_timer|request_irq|request_threaded_irq|tasklet_init|qdrv_mac_set_int_handler|qdrv_mac_set_host_dsp_int_handler|ieee80211_register_[A-Za-z_]+|ieee80211_scanner_register|ieee80211_crypto_register|ieee80211_authenticator_register|ieee80211_aclator_register)"
        for m in re.finditer(r"\b(" + calls + r")\s*\(([^;{}]*?)\)\s*;", text, re.S):
            targets = sorted({n for n in re.findall(r"\b[A-Za-z_]\w*\b", m[2]) if n in known_functions})
            registrations.append(dict(path=display_path(path), line=text.count("\n", 0, m.start()) + 1,
                                      registration=m[1], target_functions=targets,
                                      evidence="LEXICAL_CALL_ARGUMENTS_NOT_CALLGRAPH"))
        for m in re.finditer(r"\b(ieee80211_handlers|ieee80211_priv_handlers|s_msg_handler_table|s_command_table)\s*\[[^]]*\]\s*(?:\([^{};]*\))?\s*=\s*\{", text):
            start = m.end()
            level, cursor = 1, start
            while level and cursor < len(text):
                level += (text[cursor] == "{") - (text[cursor] == "}")
                cursor += 1
            body = text[start:cursor - 1]
            names = [n for n in re.findall(r"\b[A-Za-z_]\w*\b", body) if n in known_functions or n == "NULL"]
            source_tables.append(dict(path=display_path(path), line=text.count("\n", 0, m.start()) + 1,
                                      table=m[1], lexical_targets=names,
                                      evidence="ALL_CONDITIONAL_BRANCHES_RETAINED_NOT_ACTIVE_BUILD_SELECTION"))
    return dict(files=[dict(path=display_path(p), labels=sorted(labels), sha256=pins[str(p)]) for p, (labels, _) in texts.items()],
                callback_declarations=declarations, assignments=assignments, registrations=registrations,
                source_tables=source_tables, cfg80211_ops_occurrences=sum(len(re.findall(r"\bcfg80211_ops\b", t)) for _, t in texts.values())), pins


def named_paths(values: list[str]) -> dict[str, Path]:
    result = {}
    for value in values:
        name, path = value.split("=", 1)
        if not safe_identifier(name) or name in result:
            raise ValueError("invalid/duplicate input label")
        result[name] = Path(path)
    return result


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", action="append", default=[], metavar="LABEL=PATH")
    parser.add_argument("--source", action="append", default=[], metavar="LABEL=PATH")
    parser.add_argument("--root", type=Path, help="Workspace root to resolve default inputs; override for independent repository use")
    parser.add_argument("--manifest", type=Path, help="JSON with modules and sources maps; paths resolve against --root or manifest parent")
    parser.add_argument("--rea-getparam", type=Path, help="Optional exact OEM REA getparam result to bind to structural inventory")
    parser.add_argument("--rea-setparam", type=Path, help="Optional exact OEM REA setparam result to bind to structural inventory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    global ROOT
    old_root = ROOT
    if args.root:
        ROOT = args.root.resolve()
    modules = named_paths(args.module) if args.module else DEFAULT_MODULES
    sources = named_paths(args.source) if args.source else DEFAULT_SOURCES
    if args.root:
        modules = {name: ROOT / path.relative_to(old_root) if path.is_relative_to(old_root) else path for name, path in modules.items()}
        sources = {name: ROOT / path.relative_to(old_root) if path.is_relative_to(old_root) else path for name, path in sources.items()}
    if args.manifest:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        base = ROOT if args.root else args.manifest.resolve().parent
        def paths(mapping):
            return {name: Path(value) if Path(value).is_absolute() else base / value for name, value in mapping.items()}
        modules, sources = paths(data["modules"]), paths(data["sources"])
    elfs = {name: Elf(path) for name, path in modules.items()}
    inventories = {name: elf.inventory() for name, elf in elfs.items()}
    for name, elf in elfs.items():
        if "wlan" in name:
            inventories[name]["wireless_extensions"] = elf.wext_definition()
    known_functions = {s["name"] for elf in elfs.values() for s in elf.syms if s["type"] == 2 and s["name"]}
    source, pins = source_inventory(sources, known_functions)
    pins.update({str(path.resolve()): inventories[name]["sha256"] for name, path in modules.items()})
    pins[str(Path(__file__).resolve())] = sha(Path(__file__))
    ioctls = {name: elf.ioctl_records() for name, elf in elfs.items() if "wlan" in name}
    comparisons = {}
    if "oem_wlan" in ioctls and "f365_wlan" in ioctls:
        canonical = lambda rows: Counter(tuple(r[k] for k in ("cmd", "set_args", "get_args", "name")) for r in rows)
        old, new = canonical(ioctls["oem_wlan"]), canonical(ioctls["f365_wlan"])
        comparisons["oem_vs_f365_private_ioctls"] = dict(oem_entries=sum(old.values()), port_entries=sum(new.values()),
                                                       preserved=sum((old & new).values()),
                                                       missing=[list(x) for x in (old - new).elements()],
                                                       additional=[list(x) for x in (new - old).elements()])
    args.output.mkdir(parents=True, exist_ok=False)
    for name, inventory in inventories.items():
        write_json(args.output / (name + ".ops.json"), inventory)
    write_json(args.output / "source-callbacks.json", source)
    write_json(args.output / "private-ioctls.json", ioctls)
    write_json(args.output / "comparisons.json", comparisons)
    rea_provenance = {}
    for lane, path in (("getparam", args.rea_getparam), ("setparam", args.rea_setparam)):
        if path:
            evidence = json.loads(path.read_text(encoding="utf-8"))
            assert evidence["ok"] is True, "failed REA result"
            body = evidence["data"]
            rea_provenance[lane] = dict(path=display_path(path), sha256=sha(path), evidence_id=body["evidence_id"],
                                       target_sha256=body["subject"]["digest"]["sha256"],
                                       operation=body["operation"], procedure=body["raw_result"]["value"]["procedure"],
                                       limits="Independent static REA binding; no inference of complete behavior or hardware acceptance")
            pins[str(path.resolve())] = sha(path)
    if rea_provenance:
        write_json(args.output / "rea-provenance.json", rea_provenance)
    # Verify every selected original input remained byte-identical during run.
    for path, expected in pins.items():
        if sha(Path(path)) != expected:
            raise RuntimeError("input changed during read-only inventory: " + display_path(Path(path)))
    summary = {
        "schema": "openmitrastar.hgw5g-driver-ops/v1", "status": "PASS_OFFLINE_METADATA_RECOVERY",
        "hardware_accessed": False, "firmware_eligible": False, "raw_binary_data_exported": False,
        "inputs_unchanged": True,
        "modules": {name: {k: value[k] for k in ("path", "bytes", "sha256", "symbols_total", "relocation_count", "allocated_data_relocation_count", "function_pointer_relocation_count")}
                    | {"functions": len(value["functions"]), "imports": len(value["imports"]), "exports": len(value["exports"]), "callback_objects": len(value["callback_objects"])}
                    for name, value in inventories.items()},
        "source": dict(files=len(source["files"]), callback_declarations=len(source["callback_declarations"]),
                       assignments=len(source["assignments"]), registrations=len(source["registrations"]),
                       cfg80211_ops_occurrences=source["cfg80211_ops_occurrences"]),
        "independent_rea_provenance": rea_provenance,
        "comparisons": comparisons,
        "limits": [
            "All symbols and all allocated-data REL/RELA records of the selected exact modules are enumerated.",
            "Function pointer evidence is STT_FUNC or exact section-plus-addend match; unresolved records remain explicit.",
            "Names are not semantic contracts. Data references include kernel exports and metadata as well as operation tables.",
            "Mutable/BSS callback installation needs source and instruction analysis; lexical assignments are not CFG proof.",
            "Source scans are direct files only, include inactive preprocessor branches, and are not whole-tree completeness claims.",
            "No binary strings, key material, calibration bytes, raw sections or complete firmware images are exported.",
            "Modern cfg80211/mac80211 reconstruction, complete MuC/AuC firmware semantics and physical acceptance remain unproven.",
        ],
    }
    write_json(args.output / "input-hashes.json", {display_path(Path(p)): h for p, h in pins.items()})
    write_json(args.output / "result.json", summary)
    manifest = {p.name: sha(p) for p in sorted(args.output.iterdir()) if p.is_file()}
    write_json(args.output / "evidence-manifest.json", manifest)
    print(json.dumps({"status": summary["status"], "modules": len(modules),
                      "source": summary["source"], "result": str(args.output / "result.json")}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
