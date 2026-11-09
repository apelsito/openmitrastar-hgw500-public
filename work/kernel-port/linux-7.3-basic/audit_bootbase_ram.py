#!/usr/bin/env python3
"""Bounded static trace of the owner's verified Bootbase RAM image path.
No emulation, UART, network, device access, or protected-partition mutation.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib, json, lzma, re, struct

OEM_SHA = "dc1d3a792a0fc449aeeda23e91805b132846e26e2a802790c90106a278fd9b7d"
DECODED_SHA = "20ab45412b973478aa49a3daa31851a49f0deeaa09d07213479b0c3ee7af5f07"
DISASM_SHA = "65e5f48c30c59be7f787329d9135229afa7cb04dc1125f5e9bfd8fc8322cf150"
IMAGE_SHA = "24a085a69296c7f8c31dc587a231231750f66928b3480ff777f0d741aa48fbfb"
BASE = 0x88014000
ANCHORS = [
    (0x880172f2, "0026821f00000020", "add r2,r14,0x2000", "kernel payload pointer"),
    (0x880174d2, "0f0e5410", "brlo r14,0x1,14", "compression zero enters copy branch"),
    (0x88017502, "e971", "mov_s r1,r15", "copy source = selected payload"),
    (0x8801750a, "6a096002", "bl.d 18792", "calls copy wrapper at 0x8801be70"),
    (0x8801750e, "a970", "mov_s r0,r13", "delay slot passes LOAD as copy destination"),
    (0x8801be74, "96094006", "bl 51604", "wrapper calls memmove implementation 0x88028808"),
    (0x8802ccdc, "40100d26", "ld.as r13,[r16,64]", "Linux handoff reads ep field from headers"),
    (0x8802cd06, "23204003", "jl.d [r13]", "indirect transfer to selected kernel entry"),
    (0x8802cd0a, "00d8", "mov_s r0,0", "handoff supplies zero U-Boot tag"),
]
def sha(data): return hashlib.sha256(data).hexdigest()
def require(ok, reason):
    if not ok: raise ValueError(reason)

def inspect(oem, decoded, disasm, image):
    for data, expected, name in [(oem, OEM_SHA, "OEM mtd0"), (decoded, DECODED_SHA, "decoded Bootbase"),
                                  (disasm, DISASM_SHA, "retained GNU assembly"), (image, IMAGE_SHA, "selected RAM image")]:
        require(sha(data) == expected, name + " identity changed")
    expanded = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(oem[3892:])
    require(expanded == decoded, "decoded Bootbase not derived from selected OEM input")
    assembly = disasm.decode("utf-8")
    observations = []
    for address, encoded, instruction, reason in ANCHORS:
        expected = bytes.fromhex(encoded)
        require(decoded[address - BASE:address - BASE + len(expected)] == expected, "instruction bytes changed")
        line = next((s for s in assembly.splitlines() if s.startswith(f"{address:08x}:")), None)
        require(line is not None, "assembly address missing")
        # Annotation spellings remain provider-specific; source bytes pin the instruction.
        observations.append({"address": hex(address), "file_offset": address - BASE,
                             "bytes": encoded, "retained_assembly": line,
                             "interpretation": reason, "confidence": "derived-static-trace"})
    strings = {}
    for name, address in [("loading", 0x8802fe44), ("handoff", 0x880354f0)]:
        at = address - BASE
        strings[name] = decoded[at:decoded.index(0, at)].decode("ascii")
    require(strings["loading"] == "   Loading %s ... ", "copy-path message differs")
    linux_handler = struct.unpack_from("<I", decoded, 0x88035594 - BASE)[0]
    require(linux_handler == 0x8802cbc4, "Linux OS dispatch pointer differs")
    values = struct.unpack(">7I4B32s", image[:64])
    load, entry, size = values[4], values[5], values[3]
    require((load, entry, size, values[7:11]) == (0x8493a000, 0x8493e000, 1958208, (5, 19, 2, 0)),
            "image header differs from traced path")
    source_start, source_end = 0x83002000, 0x83002000 + size
    destination_end = load + size
    require(source_end < 0x84000000 < load < entry < destination_end < 0x88000000,
            "staging/scratch/load intervals overlap or exceed DDR")
    return {"schema": "openmitrastar.basic73-bootbase-static-trace/v1",
            "status": "PASS_WITHIN_STATIC_TRACE_SCOPE",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": {"oem_mtd0_sha256": OEM_SHA, "decoded_sha256": DECODED_SHA,
                       "retained_disassembly_sha256": DISASM_SHA, "image_sha256": IMAGE_SHA},
            "observations": observations, "linux_os_dispatch": hex(linux_handler),
            "source_interval": [hex(source_start), hex(source_end)],
            "destination_interval": [hex(load), hex(destination_end)],
            "entry": hex(entry), "strings": strings,
            "hardware_accessed": False, "physical_boot": "UNRUN",
            "coverage": "selected legacy-kernel payload/copy/entry paths only",
            "limitations": ["No CPU or Bootbase execution.",
                            "Copied branch traced from retained GNU disassembly, with exact bytes bound to OEM input.",
                            "Cache handoff, inherited state, coprocessor quiescence, UART/timer and return route remain physical gates.",
                            "Published GPL source corroborates generic copy semantics; the dumped binary selects the RAS offset.",
                            "No inference that iminfo alone proves a Linux boot."]}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--oem", type=Path, required=True)
    ap.add_argument("--decoded", type=Path, required=True)
    ap.add_argument("--disassembly", type=Path, required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    require(not a.output.exists(), "select an absent evidence directory")
    report = inspect(a.oem.read_bytes(), a.decoded.read_bytes(), a.disassembly.read_bytes(), a.image.read_bytes())
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "observations": len(report["observations"]),
                      "directory": str(a.output), "physical_boot": "UNRUN"}))

if __name__ == "__main__": main()
