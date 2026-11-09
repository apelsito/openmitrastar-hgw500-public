"""Prepare two source-only OEM ioctl aliases; never load/build hardware.

The only admitted entries are TX_MAXMPDU=246 set/get. Their actual source
dispatch exists in the baseline. Other missing operations remain explicitly
unimplemented; numerical forwarding is not accepted as semantics recovery.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c"
SOURCE_SHA = "4f1dc82484e7e4828ef0d68dc5b4566dd2711832a4d06191127298ccc02bc805"
HEADER = ROOT / "work/sources/Quantenna-GPL/drivers/include/shared/net80211/ieee80211_ioctl.h"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert sha(SOURCE) == SOURCE_SHA, "source pin drift"
    proof = json.loads((args.inventory / "result.json").read_text())
    assert proof["status"] == "PASS_OFFLINE_METADATA_RECOVERY"
    comparison = json.loads((args.inventory / "comparisons.json").read_text())["oem_vs_f365_private_ioctls"]
    assert (comparison["oem_entries"], comparison["port_entries"], comparison["preserved"]) == (607, 566, 563)
    assert len(comparison["missing"]) == 44 and len(comparison["additional"]) == 3
    original = SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    enums = {int(value): name for name, value in re.findall(r"\b(IEEE80211_PARAM_\w+)\s*=\s*(\d+)", header)}
    assert enums[246] == "IEEE80211_PARAM_TX_MAXMPDU"
    case = "case IEEE80211_PARAM_TX_MAXMPDU:"
    cases = [m.start() for m in re.finditer(re.escape(case), original)]
    assert len(cases) == 2, "set/get implementation missing"
    blocks = [original[start:original.index("\n\tcase ", start + len(case))] for start in cases]
    assert "IEEE80211_VHTCAP_MAX_MPDU_11454" in blocks[0] and "ieee80211_param_to_qdrv" in blocks[0]
    assert "param[0] = vap->iv_tx_max_amsdu;" in blocks[1]
    table_start = original.index("static const struct iw_priv_args ieee80211_priv_args[]")
    table_end = original.index("\n};", table_start)
    table = original[table_start:table_end]
    assert '"tx_maxmpdu"' not in table and '"get_tx_maxmpdu"' not in table
    addition = '\n\t/* Recovered OEM aliases: dispatch already exists for parameter 246. */\n\t{ IEEE80211_PARAM_TX_MAXMPDU,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "tx_maxmpdu" },\n\t{ IEEE80211_PARAM_TX_MAXMPDU,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_tx_maxmpdu" },'
    candidate = original[:table_end] + addition + original[table_end:]
    assert candidate.replace(addition, "", 1) == original
    expected_aliases = {(246, 18433, 0, "tx_maxmpdu"), (246, 0, 18433, "get_tx_maxmpdu")}
    assert expected_aliases <= {tuple(x) for x in comparison["missing"]}
    mapping = []
    for command, setter, getter, name in comparison["missing"]:
        if command == 246:
            decision = "SOURCE_ONLY_ALIAS_TO_EXISTING_SET_GET_DISPATCH"
            reason = "TX_MAXMPDU has existing enum and set/get bodies; isolated table-only patch supplied. Full module qualification required."
        elif command in (331, 275):
            decision = "NO_GO_GETTER_SEMANTICS_NOT_RECONSTRUCTED"
            reason = "Existing numeric enum and setter only; requested getter lacks dispatch case. Requires OEM instruction/ABI evidence."
        else:
            decision = "NO_GO_OEM_EXTENSION_ABI_NOT_IN_GPL_ENUM"
            reason = "Exact OEM table proves id/name/encoding. Corresponding 449+ enum and implementation are absent from retained GPL/port source."
        mapping.append(dict(cmd=command, name=name, set_args=setter, get_args=getter,
                            retained_enum=enums.get(command), decision=decision, reason=reason))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "ieee80211_wireless.c").write_text(candidate, encoding="utf-8", newline="\n")
    patch = "".join(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
                                     fromfile="a/src/wlan/ieee80211_wireless.c", tofile="b/src/wlan/ieee80211_wireless.c"))
    (args.output / "tx-maxmpdu-aliases.patch").write_text(patch, encoding="utf-8", newline="\n")
    result = dict(schema="openmitrastar.hgw5g-oem-ioctl-alias/v1", status="SOURCE_ONLY_ALIAS_CANDIDATE_NO_GO_MODULE",
                  hardware_accessed=False, firmware_eligible=False, baseline_unchanged=sha(SOURCE) == SOURCE_SHA,
                  baseline_source_sha256=SOURCE_SHA, candidate_source_sha256=sha(args.output / "ieee80211_wireless.c"),
                  header_sha256=sha(HEADER), inventory_sha256=sha(args.inventory / "result.json"),
                  patch_sha256=sha(args.output / "tx-maxmpdu-aliases.patch"),
                  source_change="Two table-only aliases; all executable source outside table is identical",
                  missing_total=44, aliases_prepared=2, unresolved=42, missing_mapping=mapping,
                  additional_port_entries=comparison["additional"],
                  controls_activation="No source dispatch, mode, radar, RF, regulatory or runtime state changed",
                  remaining_gates=["exact F365 WLAN baseline full-module equivalence", "candidate compile and table recovery 568 entries", "complete module/source delta qualification", "physical owner gates are separate and UNRUN"])
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "baseline_unchanged", "aliases_prepared", "unresolved")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
