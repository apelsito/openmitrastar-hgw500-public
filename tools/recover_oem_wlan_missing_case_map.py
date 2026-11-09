"""Map exact OEM WEXT missing ids through pinned ARC700 switch jump tables.

No source semantics are invented. Each case address is proven by the real
dispatch instructions and decoded linked pointer table. Assembly fragments are
bounded lexical spans, not complete control-flow or wire ABI proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sections(raw):
    assert raw[:6] == b"\x7fELF\x01\x01" and struct.unpack_from("<HH", raw, 16) == (2, 93)
    offset = struct.unpack_from("<I", raw, 32)[0]
    size, count, string_index = struct.unpack_from("<HHH", raw, 46)
    table = [struct.unpack_from("<10I", raw, offset + i * size) for i in range(count)]
    strings = raw[table[string_index][4]:table[string_index][4] + table[string_index][5]]
    return {strings[h[0]:strings.index(0, h[0])].decode(): dict(address=h[3], offset=h[4], size=h[5]) for h in table}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--linked", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--objdump", type=Path, required=True)
    a = p.parse_args()
    raw = a.linked.read_bytes()
    assert sha(a.linked) == "79fbcbd4634a9fc32fdf8ac0c997f3bd0329131162a1ea4948794e4986c7e40a"
    sec = sections(raw)
    assert sec[".text"]["address"] == 0x10000 and sec[".rodata"]["address"] == 0x85D50
    missing = json.loads((a.inventory / "comparisons.json").read_text())["oem_vs_f365_private_ioctls"]["missing"]
    a.output.mkdir(parents=True, exist_ok=False)
    command = [str(a.objdump), "-d", "-j", ".text", str(a.linked)]
    assembly = subprocess.check_output(command, text=True)
    (a.output / "oem-wlan-text.objdump.txt").write_text(assembly)
    parsed = []
    for line in assembly.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+", line)
        if m:
            parsed.append((int(m[1], 16), line))
    lanes = {
        "get": dict(function=0x3741C, table=0x86C30, default=0x397EA, start_id=2, count=497,
                    anchors=["sub\tr5,r6,0x2", "cmp\tr5,496", "mov\tr7,0x86c30", "ld.as\tr7,[r7,r5]", "j\t[r7]"]),
        "set": dict(function=0x41664, table=0x87714, default=0x46D24, start_id=2, count=497,
                    anchors=["sub\tr2,r17,0x2", "cmp\tr2,496", "mov\tr3,0x87714", "ld.as\tr3,[r3,r2]", "j_s\t[r3]"]),
    }
    maps = {}
    for lane, spec in lanes.items():
        assert all(anchor in assembly for anchor in spec["anchors"]), "jump dispatch assembly changed"
        table_offset = sec[".rodata"]["offset"] + spec["table"] - sec[".rodata"]["address"]
        targets = list(struct.unpack_from("<" + "I" * spec["count"], raw, table_offset))
        assert all(sec[".text"]["address"] <= target < sec[".text"]["address"] + sec[".text"]["size"] for target in targets)
        maps[lane] = {str(i + spec["start_id"]): hex(target) for i, target in enumerate(targets)}
        spec["targets"] = targets
    records = []
    for command_id, set_args, get_args, name in missing:
        lane = "set" if set_args else "get"
        spec = lanes[lane]
        start = spec["targets"][command_id - spec["start_id"]]
        later = [target for target in spec["targets"] if target > start]
        end = min(min(later) if later else start + 512, start + 512)
        snippet = [line for address, line in parsed if start <= address < end]
        assert snippet, f"no instruction span for {name}"
        filename = f"{command_id:03d}-{name}-{lane}.objdump.txt"
        (a.output / filename).write_text("\n".join(snippet) + "\n")
        records.append(dict(cmd=command_id, name=name, direction=lane, set_args=set_args, get_args=get_args,
                            case_address=hex(start), default_target=start == spec["default"],
                            span_end_exclusive=hex(end), assembly=filename,
                            instructions=len(snippet), evidence="EXACT_SWITCH_TABLE_ADDRESS_AND_ASSEMBLY_FRAGMENT",
                            semantics_status="NEEDS_CONTROL_FLOW_FIELD_ABI_AND_RETURN_RECONSTRUCTION"))
    result = dict(schema="openmitrastar.oem-wlan-missing-case-map/v1", status="PASS_OFFLINE_44_CASE_ADDRESSES_NOT_SEMANTIC_COMPLETION",
                  linked_sha256=sha(a.linked), objdump_sha256=sha(a.objdump), hardware_accessed=False,
                  firmware_eligible=False, jump_tables={key:{k: (hex(v) if k in {"function", "table", "default"} else v)
                                                            for k,v in value.items() if k != "targets"} for key,value in lanes.items()},
                  all_case_maps=maps, records=records,
                  limitation="Fragments can branch to shared code outside span; local fields/wire getters are not established by pointer mappings alone")
    (a.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (a.output / "manifest.json").write_text(json.dumps({p.name: sha(p) for p in a.output.iterdir() if p.is_file()}, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "cases": len(records)}))


if __name__ == "__main__":
    main()
