#!/usr/bin/env python3
"""Package the exact BASIC73 ELF as an uncompressed RAM-only RAS image.
Reads explicit local inputs. No router/UART/reboot/flash or network operations.
"""
from pathlib import Path
import argparse, hashlib, json, struct, zlib

ELF_SHA = "6c13ee940002b1e4512624e676cc158bc4dd3a51f7299592281fac52b39db220"
TEMPLATE_SHA = "81bbb0098f66c453c3282185ac337761a89d174950b341c6c5a6572ba4034719"
RAW_SHA = "444eeafa263d3745cc4a730d16399ab3b32c0f5f1226a8c187c38496c452ebf3"
INIT_SHA = "9380f5c7b85231ae9320fc70b7b6a922316978c61f69d473907271168ca36194"
RAS_SHA = "24a085a69296c7f8c31dc587a231231750f66928b3480ff777f0d741aa48fbfb"
LOAD, ENTRY, DDR_END = 0x8493a000, 0x8493e000, 0x88000000

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def window(data, offset, size):
    require(offset >= 0 and size >= 0 and offset + size <= len(data), "truncated ELF range")
    return data[offset:offset + size]

def elf_raw(data):
    require(len(data) >= 52, "ELF header truncated")
    h = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    require(h[0][:7] == b"\x7fELF\x01\x01\x01", "requires ELF32 little endian")
    require(h[1:4] == (2, 93, 1), "requires ARCompact executable")
    require(h[4] == ENTRY and h[8] == 52 and h[11] == 40, "ELF entry/layout changed")
    require(h[7] == 0x403, "ELF ARC ABI flags changed")
    require(0 < h[12] < 128 and h[13] < h[12], "ELF section count invalid")
    sections = [struct.unpack("<10I", window(data, h[6] + i * 40, 40)) for i in range(h[12])]
    names_section = sections[h[13]]
    names = window(data, names_section[4], names_section[5])
    allocated = []
    for section in sections:
        require(section[0] < len(names), "ELF section name invalid")
        end = names.find(b"\0", section[0])
        require(end >= 0, "ELF section name unterminated")
        name = names[section[0]:end].decode("ascii")
        if section[2] & 2 and section[5]:
            require(LOAD <= section[3] < section[3] + section[5] <= DDR_END, "allocated section outside RAM")
            allocated.append((name, section))
    require(min(s[3] for _, s in allocated) == LOAD, "ELF load address changed")
    stored = [(name, s) for name, s in allocated if s[1] != 8]
    top = max(s[3] + s[5] for _, s in stored)
    require(top - LOAD <= 0x400000, "BASIC payload exceeds bounded size")
    raw = bytearray(top - LOAD)
    previous_end = LOAD
    for name, section in sorted(stored, key=lambda x:x[1][3]):
        require(section[3] >= previous_end, "allocated ELF sections overlap")
        raw[section[3] - LOAD:section[3] - LOAD + section[5]] = window(data, section[4], section[5])
        previous_end = section[3] + section[5]
    ramfs = next((s for name, s in stored if name == ".init.ramfs"), None)
    require(ramfs is not None, "embedded initramfs missing")
    decoder = zlib.decompressobj(31)
    cpio = decoder.decompress(window(data, ramfs[4], ramfs[5])) + decoder.flush()
    require(decoder.eof and len(cpio) <= 16384, "embedded initramfs invalid")
    cursor, files = 0, []
    while cursor + 110 <= len(cpio):
        header = cpio[cursor:cursor + 110]
        require(header[:6] == b"070701", "initramfs requires newc")
        v = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        require(0 < v[11] < 128, "cpio name size invalid")
        name = window(cpio, cursor + 110, v[11])
        require(name[-1:] == b"\0", "cpio name unterminated")
        name = name[:-1].decode("ascii")
        start = (cursor + 110 + v[11] + 3) & ~3
        body = window(cpio, start, v[6])
        files.append({"name": name, "bytes": len(body), "sha256": sha(body),
                      "mode": v[1], "device_major": v[9], "device_minor": v[10]})
        cursor = (start + v[6] + 3) & ~3
        if name == "TRAILER!!!":
            break
    require(files and files[-1]["name"] == "TRAILER!!!", "cpio trailer missing")
    require(len({r["name"] for r in files}) == len(files), "duplicate initramfs entry")
    init = next((f for f in files if f["name"] == "init"), None)
    require(init and init["sha256"] == INIT_SHA and init["mode"] & 0o111, "PID1 differs from final reference")
    console = next((f for f in files if f["name"] == "dev/console"), None)
    require(console and console["mode"] & 0o170000 == 0o020000 and
            (console["device_major"], console["device_minor"]) == (5, 1), "console node differs")
    return bytes(raw), files, max(s[3] + s[5] for _, s in allocated)

def package(elf, template):
    require(sha(elf) == ELF_SHA, "kernel hash differs from sealed v6")
    require(sha(template) == TEMPLATE_SHA, "OEM template hash differs")
    raw, files, memory_end = elf_raw(elf)
    require(len(raw) == 1958208 and sha(raw) == RAW_SHA, "reconstructed raw differs from sealed v6")
    fields = [0x27051956, 0, 1792365298, len(raw), LOAD, ENTRY,
              zlib.crc32(raw) & 0xffffffff, 5, 0x13, 2, 0,
              b"OpenMitraStar 7.3 BASIC UART".ljust(32, b"\0")]
    fields[1] = zlib.crc32(struct.pack(">7I4B32s", *fields)) & 0xffffffff
    result = struct.pack(">7I4B32s", *fields) + template[64:8192] + raw
    require(sha(result) == RAS_SHA and len(result) == 1966400, "RAM artifact differs from sealed v7")
    return result, {"kernel_sha256": ELF_SHA, "raw_sha256": RAW_SHA, "initramfs": files,
                    "memory_end": hex(memory_end), "compression": 0}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf", type=Path, required=True)
    p.add_argument("--template", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    require(not a.output.exists(), "select an absent output directory")
    image, details = package(a.elf.read_bytes(), a.template.read_bytes())
    report = {"schema": "openmitrastar.basic73-ram-package/v1", "status": "PASS_EXACT_OFFLINE_PACKAGE",
              "check_only": a.check_only, "hardware_accessed": False, "physical_boot": "UNRUN",
              "bytes": len(image), "sha256": sha(image), "crc32": f"{zlib.crc32(image) & 0xffffffff:08x}",
              **details}
    if not a.check_only:
        a.output.mkdir(parents=True, exist_ok=False)
        (a.output / "basic73-RAM-ONLY-NO-GO.ras.bin").write_bytes(image)
        (a.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
