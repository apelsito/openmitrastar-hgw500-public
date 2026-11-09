"""Measure every OEM private-table gap against an offline-qualified module.

Reads immutable local artifacts only. Table membership is not full feature
acceptance; firmware consumers, ownership, RF and physical gates stay separate.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from build_hgw5g_remaining_ops_ledger import DETAILS
from recover_hgw5g_driver_ops import Elf

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "repos/openmitrastar-hgw500-quantenna-5ghz-driver"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return tuple(row[k] for k in ("cmd", "set_args", "get_args", "name"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = json.loads(args.qualification.read_text(encoding="utf-8"))
    assert proof["status"].startswith("PASS_OFFLINE"), "module not offline-qualified"
    expected = [x for x in proof["modules"] if x.get("component", x.get("name")) == "wlan"
                or (x.get("component", x.get("name")) is None and Path(x["path"]).name == "wlan.ko")]
    assert expected and all(x["sha256"] == sha(args.module) for x in expected)
    original_path = REPO / "evidence/ops-repository-20261022-r1/private-ioctls.json"
    original = json.loads(original_path.read_text(encoding="utf-8"))["oem_wlan"]
    current = Elf(args.module).ioctl_records()
    old_counts, new_counts = Counter(map(key, original)), Counter(map(key, current))
    missing, added = old_counts - new_counts, new_counts - old_counts
    baseline_path = REPO / "evidence/ops-repository-20261022-r1/comparisons.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert len(original) == 607
    count = sum(missing.values())
    assert len(current) == proof.get("private_table_records", proof.get("private_records"))
    assert count == proof.get("remaining_original_table_gaps", proof.get("remaining_original_records"))
    records = []
    for (cmd, set_args, get_args, name), occurrences in missing.items():
        detail = dict(DETAILS[cmd])
        if cmd == 461:
            detail["dependency"] = (
                "OEM channel-set selection requires 80-byte tables, allocation/free, "
                "seven metric-history cells, scan callbacks and band/width policies. "
                "Fresh start/pick REA retained; matching subsystem is absent from port."
            )
        records.append(dict(cmd=cmd, name=name, direction="set" if set_args else "get",
                            set_args=set_args, get_args=get_args, occurrences=occurrences,
                            evidence=detail, status="OEM_TABLE_GAP_NOT_RECOVERED_IN_THIS_MODULE"))
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(schema="openmitrastar.qualified-private-operation-ledger/v1",
                  status="PASS_EXACT_QUALIFIED_TABLE_LEDGER_NOT_COMPLETE_DRIVER",
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  hardware_accessed=False, firmware_eligible=False,
                  qualification_status=proof["status"],
                  original_table_records=len(original), private_table_records=len(current),
                  original_records_matched=sum((old_counts & new_counts).values()),
                  original_table_gaps=count, baseline_original_table_gaps=44,
                  original_records_recovered_from_baseline=44-count,
                  port_additions=sum(added.values()), records=records,
                  inputs={str(args.qualification.resolve()): sha(args.qualification),
                          str(args.module.resolve()): sha(args.module),
                          str(original_path): sha(original_path),
                          str(baseline_path): sha(baseline_path)},
                  limitations=[
                      "Counts are private WEXT records, including separate set/get aliases.",
                      "Matching table membership does not establish all OEM behaviors.",
                      "Prototypes in other candidates are not silently included.",
                      "RF, association, traffic, persistence, rollback and release remain unrun.",
                  ])
    (args.output / "result.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    lines = ["# Exact remaining OEM private records", "",
             f"Measured at {result['created_utc']} against `{sha(args.module)}`.", "",
             f"OEM: 607 records. Qualified candidate: {len(current)}. "
             f"OEM matches: {result['original_records_matched']}. Missing: {count}. "
             f"Port additions: {result['port_additions']}.", "",
             "These are table records. Full firmware behaviors and physical acceptance are separate.", "",
             "| ID | Direction | Name | Remaining dependency |",
             "| --- | --- | --- | --- |"]
    for row in records:
        dep = row["evidence"]["dependency"].replace("|", "\\|")
        lines.append(f"| {row['cmd']} | {row['direction']} | `{row['name']}` | {dep} |")
    (args.output / "LEDGER.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "private_table_records", "original_table_gaps")}))


if __name__ == "__main__":
    main()
