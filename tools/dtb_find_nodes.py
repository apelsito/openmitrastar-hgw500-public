#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path


FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def align4(n: int) -> int:
    return (n + 3) & ~3


def cstr(data: bytes, off: int) -> str:
    end = data.find(b"\0", off)
    if end < 0:
        end = len(data)
    return data[off:end].decode("ascii", "replace")


def fmt_value(data: bytes) -> str:
    if not data:
        return "<empty>"
    if data.endswith(b"\0") and all((b == 0 or 32 <= b < 127) for b in data):
        parts = [p.decode("ascii", "replace") for p in data.rstrip(b"\0").split(b"\0")]
        return ", ".join(repr(p) for p in parts)
    if len(data) % 4 == 0:
        vals = struct.unpack(">" + "I" * (len(data) // 4), data)
        if len(vals) <= 8:
            return " ".join(f"0x{v:08x}" for v in vals)
    return data.hex()


def parse(path: Path):
    blob = path.read_bytes()
    hdr = struct.unpack_from(">10I", blob, 0)
    magic, totalsize, off_struct, off_strings, _off_rsv, version, _last, _boot, size_strings, size_struct = hdr
    if magic != 0xD00DFEED:
        raise SystemExit(f"not an FDT blob: magic=0x{magic:08x}")
    strings = blob[off_strings : off_strings + size_strings]
    p = off_struct
    end = off_struct + size_struct
    stack = []
    nodes = []

    while p < end:
        token = struct.unpack_from(">I", blob, p)[0]
        p += 4
        if token == FDT_BEGIN_NODE:
            z = blob.find(b"\0", p)
            name = blob[p:z].decode("ascii", "replace")
            p = align4(z + 1)
            if not name:
                name = "/"
            parent = stack[-1]["path"] if stack else ""
            if name == "/":
                full = "/"
            elif parent in ("", "/"):
                full = "/" + name
            else:
                full = parent + "/" + name
            node = {"name": name, "path": full, "props": []}
            nodes.append(node)
            stack.append(node)
        elif token == FDT_END_NODE:
            if stack:
                stack.pop()
        elif token == FDT_PROP:
            length, nameoff = struct.unpack_from(">II", blob, p)
            p += 8
            value = blob[p : p + length]
            p = align4(p + length)
            if stack:
                stack[-1]["props"].append((cstr(strings, nameoff), value))
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise SystemExit(f"bad token {token} at 0x{p - 4:x}")
    return nodes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dtb", type=Path)
    ap.add_argument("patterns", nargs="+")
    args = ap.parse_args()

    nodes = parse(args.dtb)
    pats = [p.lower() for p in args.patterns]
    for node in nodes:
        hay = node["path"].lower() + "\n" + "\n".join(
            f"{k} {fmt_value(v)}".lower() for k, v in node["props"]
        )
        if not any(p in hay for p in pats):
            continue
        print(f"## {node['path']}")
        for key, value in node["props"]:
            print(f"- {key}: {fmt_value(value)}")
        print()


if __name__ == "__main__":
    main()
