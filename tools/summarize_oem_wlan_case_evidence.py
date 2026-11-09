"""Bind missing-operation switch addresses to REA case excerpts and decisions.

Exports bounded static findings, not payloads, source replacements or hardware
claims. Operand offsets refer only to the exact pinned OEM ABI, never the port.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases(text):
    matches = list(re.finditer(r"^  case (0x[0-9a-f]+|[0-9]+):", text, re.M))
    result = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else text.rfind("\n  }")
        cursor = i
        while not text[match.end():end].strip() and cursor + 1 < len(matches):
            cursor += 1
            end = matches[cursor + 1].start() if cursor + 1 < len(matches) else text.rfind("\n  }")
        result[int(match[1], 0)] = text[match.start():end]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--map", type=Path, required=True)
    p.add_argument("--getparam", type=Path, required=True)
    p.add_argument("--setparam", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    mapping = json.loads(a.map.read_text())
    evidence = {"get": json.loads(a.getparam.read_text()), "set": json.loads(a.setparam.read_text())}
    assert all(x["ok"] for x in evidence.values())
    parsed = {key: cases(x["data"]["raw_result"]["value"]["pseudocode"]) for key, x in evidence.items()}
    a.output.mkdir(parents=True, exist_ok=False)
    records = []
    for row in mapping["records"]:
        lane = row["direction"]
        body = parsed[lane].get(row["cmd"], "")
        if row["default_target"]:
            classification = "OEM_EXPLICIT_UNSUPPORTED"
            decision = "Retain EOPNOTSUPP; OEM advertised entry alone does not establish an implementation."
        elif row["cmd"] == 246:
            classification = "SOURCE_ALIAS_TO_EXISTING_IMPLEMENTATION"
            decision = "Two table aliases can be rebuilt against existing validated source dispatch."
        elif row["cmd"] == 450 and lane == "get":
            classification = "OEM_CONSTANT_GETTER_70_SECONDS"
            decision = "Read-only getter can use existing MIN_CAC_PERIOD=70; requires enum/table/dispatch and qualified module delta."
        elif lane == "get" and row["case_address"] == "0x37bea":
            classification = "OEM_QDRV_GETTER_FORWARDING"
            decision = "Do not add an alias alone: F365 QDRV lacks these output cases and returns success without filling value. Reconstruct OEM QDRV/MuC output first."
        elif row["cmd"] in (463, 483) and lane == "set":
            classification = "OEM_QDRV_SETTER_FORWARDING"
            decision = "Reconstruct downstream QDRV wire semantics and accepted value contract before numerical forwarding."
        elif row["cmd"] == 457:
            classification = "OEM_SHARED_NAC_STATE_OR_COMMAND"
            decision = "Getter packs shared NAC stats; setter forwards to QDRV. Existing shared pointer must be ABI-qualified; raw address translation is not source recovery."
        else:
            classification = "OEM_LOCAL_STATE_POLICY_OR_INDIRECT_CALLBACK"
            decision = "Identify matching port fields, flags, callback ABI, validation and shared branch before reconstruction. OEM byte offsets must never be used in the port."
        filename = f"{row['cmd']:03d}-{row['name']}-{lane}.derived.c"
        if body:
            (a.output / filename).write_text("/* Derived REA pseudocode; verify assembly and exact OEM ABI. */\n" + body)
        records.append({**row, "classification": classification, "decision": decision,
                        "rea_case_excerpt": filename if body else None,
                        "rea_case_observed": bool(body) or row["default_target"],
                        "field_offsets_are_oem_only": True})
    result = dict(schema="openmitrastar.oem-wlan-44-evidence/v1", status="PASS_STATIC_CASE_EVIDENCE_NOT_COMPLETE_DRIVER",
                  hardware_accessed=False, firmware_eligible=False, source_replacement=False,
                  classification_counts=dict(Counter(row["classification"] for row in records)), records=records,
                  provenance={"case_map_sha256": sha(a.map), "getparam_sha256": sha(a.getparam), "setparam_sha256": sha(a.setparam),
                              "getparam_evidence_id": evidence["get"]["data"]["evidence_id"],
                              "setparam_evidence_id": evidence["set"]["data"]["evidence_id"]},
                  limits=["Static case targets and bounded REA excerpts; assembly is the ordering authority.",
                          "Pseudocode can misidentify types, signedness and shared control flow.",
                          "No physical execution, client traffic, capability enablement or completed rewrite is claimed."])
    (a.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (a.output / "manifest.json").write_text(json.dumps({x.name: sha(x) for x in a.output.iterdir() if x.is_file()}, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "classification_counts": result["classification_counts"]}))


if __name__ == "__main__":
    main()
