"""Add proven callback symbols to a new analysis ELF, preserving all load bytes.

OEM locals are stripped. REA recognized the init callback store but did not
create a Function at the actual target. This symbol-only derivative makes that
entry discoverable without changing any allocated section or original module.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocated(path):
    raw = path.read_bytes()
    offset = struct.unpack_from("<I", raw, 32)[0]
    size, count, string_index = struct.unpack_from("<HHH", raw, 46)
    table = [struct.unpack_from("<10I", raw, offset + i * size) for i in range(count)]
    strings = raw[table[string_index][4]:table[string_index][4] + table[string_index][5]]
    return {strings[h[0]:strings.index(0, h[0])].decode(): (h[1], h[2], h[3], h[5], h[8], raw[h[4]:h[4]+h[5]] if h[1] != 8 else b"")
            for h in table if h[2] & 2}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--init-evidence", type=Path, required=True)
    p.add_argument("--objcopy", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    source_sha = sha(a.input)
    assert source_sha == "60a15998175652d70fa4e1e75a6e1ee997a2e5144f9fe446af06f66641717f77"
    evidence = json.loads(a.init_evidence.read_text())
    assert evidence["ok"] and evidence["data"]["subject"]["digest"]["sha256"] == source_sha
    pseudocode = evidence["data"]["raw_result"]["value"]["pseudocode"]
    assert "(iVar4 + 0x5424) = &LAB_ram_00040730" in pseudocode
    a.output.mkdir(parents=True, exist_ok=False)
    target = a.output / "qdrv-OEM-CALLBACK-ANALYSIS_ONLY-NOT_FIRMWARE.elf"
    command = [str(a.objcopy), "--add-symbol", "om_oem_qdrv_getparam=.text:0x30730,global,function", str(a.input), str(target)]
    proc = subprocess.run(command, capture_output=True)
    (a.output / "stdout.txt").write_bytes(proc.stdout)
    (a.output / "stderr.txt").write_bytes(proc.stderr)
    assert proc.returncode == 0
    assert allocated(a.input) == allocated(target), "allocated section bytes/layout changed"
    assert sha(a.input) == source_sha
    result = dict(status="PASS_SYMBOL_ONLY_ANALYSIS_DERIVATIVE", classification="ANALYSIS_ONLY_NEVER_LOAD_OR_FLASH",
                  source_sha256=source_sha, derived_sha256=sha(target), derived=str(target), hardware_accessed=False,
                  original_unchanged=True, allocated_sections_byte_identical=True,
                  label=dict(name="om_oem_qdrv_getparam", offset=".text+0x30730", linked_address="0x40730",
                             provenance="Exact init REA store at ic+0x5424 plus OEM ET_REL relocation"),
                  init_evidence_sha256=sha(a.init_evidence), objcopy_sha256=sha(a.objcopy), command=command,
                  limit="Symbol name is analyst metadata; entry bytes and callback ownership are proven, full semantic equivalence is not")
    (a.output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
