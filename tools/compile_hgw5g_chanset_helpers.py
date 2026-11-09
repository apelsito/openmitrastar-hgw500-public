"""Compile isolated recovered461 C helpers with the pinned ARC kernel flags.

New object is for offline source/layout evidence only, never a firmware module.
Uses the WLAN retained flags and first-priority local headers, verifies pins.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import build_hgw5g_typed_header_closure as build
from recover_hgw5g_driver_ops import Elf


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scan-adapter", action="store_true")
    parser.add_argument("--transaction", action="store_true")
    args = parser.parse_args()
    assert not args.output.exists()
    source = args.candidate/"openmitrastar_chanset_recovered.c"
    cmd = build.wb.command("ieee80211_wireless", args.output, source)
    cmd[1:1] = ["-I"+str(args.candidate.resolve())]
    template = build.wb.OLD/".ieee80211_wireless.o.cmd"
    paths = {Path(__file__).resolve(), Path(build.__file__), Path(build.wb.__file__),
             template, build.qb.context.CONTEXT/".config", Path(str(build.qb.context.TC)+"gcc")}
    paths.update(p for p in args.candidate.iterdir() if p.is_file())
    for tree in ("include/generated", "include/config", "arch/arc/include/generated"):
        paths.update(p for p in (build.qb.context.CONTEXT/tree).rglob("*") if p.is_file())
    for row in template.read_text().splitlines()[1:]:
        token = row.strip().removesuffix("\\").strip()
        if not token or token.startswith(("$", "deps_", "source_")) or ":" in token or " " in token:
            continue
        token = token.replace("/home/user/mitrastar-linux-5.10.260", str(build.qb.context.KERNEL))
        path = Path(token) if token.startswith("/") else build.qb.context.CONTEXT/token
        if path.is_file():
            paths.add(path)
    pins = {str(p):sha(p) for p in paths}
    args.output.mkdir(parents=True)
    (args.output/"input-pins.json").write_text(json.dumps(pins, indent=2)+"\n")
    (args.output/"compile.command.json").write_text(json.dumps(cmd, indent=2)+"\n")
    result = dict(status="NO_GO_ARC_CHANSET_HELPERS", hardware_accessed=False, firmware_eligible=False)
    try:
        proc = subprocess.run(cmd, cwd=build.qb.context.CONTEXT, capture_output=True, timeout=180)
        (args.output/"compile.stderr").write_bytes(proc.stderr)
        assert not proc.returncode, proc.stderr.decode(errors="replace")[-3000:]
        dependencies = (args.output/"ieee80211_wireless.d").read_text().split(":",1)[1].replace("\\\n", " ").split()
        captured = {os.path.abspath(p) for p in pins}
        missing = {os.path.abspath(Path(p) if p.startswith("/") else build.qb.context.CONTEXT/p) for p in dependencies}-captured
        assert not missing, "uncaptured dependencies " + repr(sorted(missing))
        obj = args.output/"ieee80211_wireless.o"
        elf = Elf(obj)
        functions = [s["name"] for s in elf.syms if s["type"]==2 and s["size"]]
        intended={"om_chanset_template", "om_chanset_find", "om_chanset_add_scan_type", "om_chanset_rank_defaults", "om_chanset_edges", "om_chanset_cost"}
        if args.scan_adapter:
            intended.update({"om_chanset_normalize_sample", "om_chanset_update_scan_entry", "om_chanset_select", "om_cs_scale"})
        if args.transaction:
            assert args.scan_adapter, "transaction requires scan adapter"
            intended.update({"om_chanset_prepare", "om_chanset_scan_request", "om_chanset_scan_advance", "om_chanset_scan_sample", "om_chanset_end"})
        inherited={"bus_to_virt", "muc_to_nocache", "nocache_to_muc"}
        assert set(functions)==intended|inherited, "unexpected compiled functions " + repr(functions)
        tables = [s for s in elf.syms if s["name"].startswith("om_cs_band")]
        assert sum(s["size"] for s in tables)==10400
        for path,digest in pins.items():
            assert sha(path)==digest, "input drift " + path
        status="PASS_ARC_COMPILED461_TRANSACTION_HELPERS_EXACT130_TABLES" if args.transaction else ("PASS_ARC_COMPILED461_NINE_HELPERS_EXACT130_TABLES" if args.scan_adapter else "PASS_ARC_COMPILED461_SIX_HELPERS_EXACT130_TABLES")
        result.update(status=status, input_pins=len(pins),
                      inputs_unchanged=True, object_bytes=obj.stat().st_size, object_sha256=sha(obj),
                      functions=functions, intended_helpers=sorted(intended),
                      retained_header_functions=sorted(inherited), table_bytes=10400, machine=93,
                      limits="Standalone object only; no registration/driver integration/physical acceptance")
    except Exception as error:
        result["error"]=str(error)
    (args.output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    return int(not result["status"].startswith("PASS_"))


if __name__=="__main__":
    raise SystemExit(main())
