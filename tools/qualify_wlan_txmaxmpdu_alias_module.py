"""Qualify complete WLAN delta for two exact OEM TX_MAXMPDU aliases, offline only.

Every executable/data section, symbol and relocation is compared after only
the declared table insertion, count, diagnostic line numbers and metadata delta.
No file is patched or loaded. Output is new immutable qualification evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from qualify_f370_qdrv_module import Elf, baseline_compare
from recover_hgw5g_driver_ops import Elf as MetadataElf


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def one(elf, name):
    rows = [s for s in elf.syms if s["name"] == name]
    assert len(rows) == 1, name
    return rows[0]


def arc32me(value):
    return struct.pack("<HH", value >> 16, value & 65535)


def normalize_candidate(baseline, candidate):
    old_table = one(baseline, "ieee80211_priv_args")
    new_table = one(candidate, "ieee80211_priv_args")
    assert baseline.symsection(old_table) == candidate.symsection(new_table) == ".rodata"
    assert old_table["value"] == new_table["value"] and old_table["size"] == 566 * 24 and new_table["size"] == 568 * 24
    cut = old_table["value"] + old_table["size"]
    extra = candidate.byname[".rodata"]["data"][cut:cut + 48]
    expected = b"".join(struct.pack("<IHH", 246, setter, getter) + name.encode().ljust(16, b"\0")
                        for setter, getter, name in ((18433, 0, "tx_maxmpdu"), (0, 18433, "get_tx_maxmpdu")))
    assert extra == expected, "exact added 24-byte aliases"
    handlers_old = one(baseline, "ieee80211_iw_handler_def")
    handlers_new = one(candidate, "ieee80211_iw_handler_def")
    assert handlers_old == handlers_new and baseline.symsection(handlers_old) == ".data"
    data = bytearray(candidate.byname[".data"]["data"])
    count = handlers_new["value"] + 8
    assert struct.unpack_from("<H", baseline.byname[".data"]["data"], count)[0] == 566
    assert struct.unpack_from("<H", data, count)[0] == 568
    struct.pack_into("<H", data, count, 566)
    candidate.byname[".data"]["data"] = bytes(data)
    rodata = candidate.byname[".rodata"]
    rodata["data"] = rodata["data"][:cut] + rodata["data"][cut + 48:]
    rodata["size"] -= 48
    changed_diagnostics = []
    before = one(baseline, "ieee80211_delete_wlanunit")
    after = one(candidate, "ieee80211_delete_wlanunit")
    assert before == after
    section = baseline.symsection(before)
    old_code = baseline.byname[section]["data"][before["value"]:before["value"] + before["size"]]
    new_data = bytearray(candidate.byname[section]["data"])
    for relative, old_line, new_line in ((0x26, 0x5261, 0x5266), (0x6E, 0x5262, 0x5267)):
        offset = before["value"] + relative
        assert old_code[relative:relative + 8] == bytes.fromhex("0a22800f") + arc32me(old_line)
        assert new_data[offset:offset + 8] == bytes.fromhex("0a22800f") + arc32me(new_line)
        new_data[offset + 4:offset + 8] = arc32me(old_line)
        changed_diagnostics.append({"function": before["name"], "relative_instruction_offset": relative,
                                    "old_source_line": old_line, "new_source_line": new_line,
                                    "instruction": "mov r2,line; existing assertion diagnostic"})
    candidate.byname[section]["data"] = bytes(new_data)
    shifted_symbols = []
    for symbol in candidate.syms:
        if symbol["name"] == "ieee80211_priv_args":
            symbol["size"] -= 48
        if candidate.symsection(symbol) == ".rodata" and symbol["value"] >= cut + 48:
            shifted_symbols.append({"symbol": symbol["name"], "old_value": symbol["value"] - 48, "new_value": symbol["value"]})
            symbol["value"] -= 48
    shifted_relocations = []
    for relocation in candidate.relas:
        if relocation["section"] == ".rodata" and relocation["offset"] >= cut + 48:
            shifted_relocations.append({"kind": "relocation_site", "section": ".rodata",
                                        "old_offset": relocation["offset"] - 48, "new_offset": relocation["offset"]})
            relocation["offset"] -= 48
        target = candidate.syms[relocation["symbol"]]
        if candidate.symsection(target) == ".rodata" and target["type"] == 3 and relocation["addend"] >= cut + 48:
            shifted_relocations.append({"section": relocation["section"], "offset": relocation["offset"],
                                        "old_addend": relocation["addend"] - 48, "new_addend": relocation["addend"]})
            relocation["addend"] -= 48
    return {"table_baseline_entries": 566, "table_candidate_entries": 568, "table_insertion_bytes": 48,
            "diagnostic_lines": changed_diagnostics, "shifted_symbols": shifted_symbols, "shifted_relocations": shifted_relocations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-build", type=Path, required=True)
    parser.add_argument("--candidate-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), "immutable output exists"
    assert args.output.name.startswith("driver5g-ops-")
    baseline_path = args.baseline_build / "a/wlan.ko"
    candidate_path = args.candidate_build / "a/wlan.ko"
    proof = json.loads((args.candidate_build / "result.json").read_text())
    baseline_proof = json.loads((args.baseline_build / "result.json").read_text())
    assert baseline_proof["status"] == "PASS_OFFLINE_FULL_BASELINE_EQUIVALENT_DECLARED_SRCVERSION"
    assert baseline_proof["metadata_delta"] == ["srcversion"] and baseline_proof["reproducible"] and not baseline_proof["comparison_errors"]
    assert sha(baseline_path) == sha(args.baseline_build / "b/wlan.ko") == baseline_proof["modules"][0]["sha256"]
    assert proof["status"] == "PASS_FULL_LINKED_MODULE_PENDING_DELTA_QUALIFICATION" and proof["reproducible"]
    assert sha(candidate_path) == sha(args.candidate_build / "b/wlan.ko") == proof["modules"][0]["sha256"]
    args.output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "openmitrastar.wlan-txmaxmpdu-alias-qualification/v1", "status": "NO_GO_MODULE_DELTA",
              "hardware_accessed": False, "firmware_eligible": False, "physical_gates": "UNRUN",
              "parent_module_sha256": sha(baseline_path), "candidate_module_sha256": sha(candidate_path),
              "limits": "Two WEXT aliases only; forty-two missing OEM private entries remain unresolved. No runtime/client/traffic/persistence/release acceptance."}
    try:
        pins = json.loads((args.candidate_build / "input-pins.json").read_text())
        for path, digest in pins.items():
            assert sha(path) == digest, "build input changed: " + path
        baseline, candidate = Elf(baseline_path), Elf(candidate_path)
        old_metadata = baseline.byname[".modinfo"]["data"].split(b"\0")
        new_metadata = candidate.byname[".modinfo"]["data"].split(b"\0")
        assert Counter(old_metadata) == Counter(new_metadata), "candidate metadata must exactly match reconstructed baseline"
        version = [x.decode().split("=", 1)[1] for x in old_metadata if x.startswith(b"srcversion=")]
        assert version == ["9A233B0BD384175810C9191"]
        result["source_identity_contract"] = {"original_f365_srcversion": "C90B1F07BF94C284D7647F7",
                                              "reconstructed_baseline_srcversion": version[0], "candidate_srcversion": version[0],
                                              "original_to_rebuild_delta_declared_in_baseline": True,
                                              "candidate_metadata_exact_to_rebuilt_baseline": True}
        assert len(baseline.relas) == len(candidate.relas) and len(baseline.syms) == len(candidate.syms)
        contract = normalize_candidate(baseline, candidate)
        comparison = baseline_compare(baseline, candidate)
        assert comparison["status"] == "PASS_FULL_BASELINE_RECONSTRUCTION", comparison["errors"]
        original_ioctls = MetadataElf(baseline_path).ioctl_records()
        candidate_ioctls = MetadataElf(candidate_path).ioctl_records()
        fields = lambda record: (record["cmd"], record["set_args"], record["get_args"], record["name"])
        old, new = Counter(map(fields, original_ioctls)), Counter(map(fields, candidate_ioctls))
        assert len(original_ioctls) == 566 and len(candidate_ioctls) == 568
        assert not old - new and new - old == Counter({(246, 18433, 0, "tx_maxmpdu"): 1, (246, 0, 18433, "get_tx_maxmpdu"): 1})
        (args.output / "declared-delta-contract.json").write_text(json.dumps(contract, indent=2) + "\n")
        (args.output / "normalized-full-module-comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
        result.update(status="PASS_OFFLINE_COMPLETE_MODULE_TWO_ALIASES", imports_unchanged=True, exports_unchanged=True,
                      table_baseline_entries=566, table_candidate_entries=568, aliases_added=2, unresolved_oem_private_entries=42,
                      complete_function_count=comparison["function_count"], relocations_all_qualified=comparison["relocations_total"],
                      symbols_all_qualified=comparison["symbols_total"], baseline_code_bytes=comparison["code_allocated_bytes"],
                      only_declared_table_count_layout_diagnostic_delta=True,
                      candidate_bytes=candidate_path.stat().st_size, reproducible=True, protected_inputs_unchanged=True)
    except Exception as exc:
        result["error"] = str(exc)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return int(result["status"] != "PASS_OFFLINE_COMPLETE_MODULE_TWO_ALIASES")


if __name__ == "__main__":
    raise SystemExit(main())
