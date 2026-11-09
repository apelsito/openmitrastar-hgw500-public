"""Compose source-built modules with one validated retained export contract.

Preserves historical composers and evidence. Rejects conflicting CRC/type/
namespace/owner declarations, removes exports provided by candidate objects,
requires all strong imports to resolve and runs one joint modpost. No hardware.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import build_hgw5g_typed_header_closure as build
from recover_hgw5g_driver_ops import Elf


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owner_name(value):
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    return value[:-3] if value.endswith(".ko") else value


def exports_of(elf, component):
    result = {}
    for sym in elf.syms:
        if not sym["name"].startswith("__ksymtab_"):
            continue
        name = sym["name"][len("__ksymtab_"):]
        sec = elf.sections[sym["section"]]["name"]
        kind = "EXPORT_SYMBOL_GPL" if sec.startswith("___ksymtab_gpl+") else "EXPORT_SYMBOL"
        assert sec in ("___ksymtab+"+name, "___ksymtab_gpl+"+name), "unknown export type " + sec
        matches = [x for x in elf.syms if x["name"] == "__kstrtabns_"+name]
        assert len(matches) == 1, "export namespace symbol absent/duplicate " + name
        ns = matches[0]
        raw = elf.sections[ns["section"]]["data"]
        namespace = raw[ns["value"]:].split(b"\0", 1)[0].decode("ascii")
        assert name not in result, "duplicate export " + name
        result[name] = dict(owner=component, kind=kind, namespace=namespace)
    return result


def deduplicate(paths, candidate_exports):
    retained = {}
    duplicates = 0
    rows_seen = 0
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            fields = line.split("\t")
            assert 4 <= len(fields) <= 5, "invalid symvers row"
            fields += [""] * (5-len(fields))
            crc, name, owner, kind, namespace = fields
            assert crc.startswith("0x") and len(crc) == 10
            int(crc, 16)
            row = (crc.lower(), owner_name(owner), kind, namespace)
            previous = retained.get(name)
            assert previous is None or previous == row, "conflicting retained export " + name
            if previous is not None:
                duplicates += 1
            retained[name] = row
            rows_seen += 1
    replaced = {}
    for name, contract in candidate_exports.items():
        if name not in retained:
            continue
        old = retained.pop(name)
        assert old[0] == "0x00000000", "nonzero CRC requires explicit candidate CRC witness " + name
        assert old[1:] == (contract["owner"], contract["kind"], contract["namespace"]), "candidate export contract conflict " + name
        replaced[name] = old
    lines = ["\t".join((crc, name, owner, kind, namespace))
             for name, (crc, owner, kind, namespace) in sorted(retained.items())]
    return "\n".join(lines)+"\n", retained, dict(input_rows=rows_seen,
            exact_duplicates_removed=duplicates, unique_external_exports=len(retained),
            candidate_providers_replaced=len(replaced), contract_conflicts=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-build", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--lane", choices=["a", "b"], default="a")
    parser.add_argument("--qdrv-baseline-build", type=Path, required=True)
    parser.add_argument("--wlan-baseline-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    source_result = args.source_build / "result.json"
    proof = json.loads(source_result.read_text())
    assert proof["status"] in ("NO_GO_TYPED_HEADER_CLOSURE", "PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA")
    qsrc, wsrc, headers = [args.candidate / x for x in ("source/qdrv", "source/wlan", "headers")]
    groups = [("qdrv", build.parse_names(qsrc)),
              ("wlan", json.loads((args.wlan_baseline_build/"result.json").read_text())["units"]),
              *[(component, [name]) for component, name in build.PROVIDERS.items()]]
    assert sum(len(names) for _, names in groups) == 58
    pinmap = json.loads((args.source_build / "input-pins.json").read_text())
    paths = {Path(__file__), Path(build.__file__), source_result,
             args.source_build/"input-pins.json", args.candidate/"result.json",
             args.qdrv_baseline_build/"dependencies.symvers", args.wlan_baseline_build/"dependencies.symvers"}
    for component, names in groups:
        for name in names:
            old = args.source_build/args.lane/component
            paths.update(old/(name+suffix) for suffix in (".o", ".d"))
            paths.update([old/("."+name+".o.cmd"), old/("compile-"+name+".command.json")])
    for path in paths:
        pinmap[str(path)] = sha(path)
    for path, digest in pinmap.items():
        assert sha(path) == digest, "input drift " + path
    args.output.mkdir(parents=True)
    (args.output/"input-pins.json").write_text(json.dumps(pinmap, indent=2)+"\n")
    result = dict(status="NO_GO_DEDUP_JOINT_COMPOSITION", hardware_accessed=False,
                  firmware_eligible=False, baseline_objects_used=False,
                  source_c_units=58, source_lane=args.lane, modules=[])
    try:
        linked, candidate_exports, elfs = [], {}, {}
        for component, names in groups:
            folder = args.output/component
            folder.mkdir()
            old = args.source_build/args.lane/component
            for name in names:
                for suffix in (".o", ".d"):
                    shutil.copyfile(old/(name+suffix), folder/(name+suffix))
                shutil.copyfile(old/("."+name+".o.cmd"), folder/("."+name+".o.cmd"))
            objects = [str(folder/(name+".o")) for name in names]
            (folder/(component+".mod")).write_text("\n".join(objects)+"\n")
            obj = folder/(component+".o")
            build.run([str(build.qb.context.TC)+"ld", "-r", "-z", "noexecstack", "--no-warn-rwx-segments", "-o", str(obj), *objects], folder, folder/"link-relocatable")
            linked.append(str(obj))
            elf = Elf(obj)
            elfs[component] = elf
            for name, contract in exports_of(elf, component).items():
                assert name not in candidate_exports, "multiple candidate providers " + name
                candidate_exports[name] = contract
        dep_paths = [args.qdrv_baseline_build/"dependencies.symvers", args.wlan_baseline_build/"dependencies.symvers"]
        text, retained, receipt = deduplicate(dep_paths, candidate_exports)
        (args.output/"retained-dependencies.symvers").write_text(text)
        closure = []
        for component, elf in elfs.items():
            imports = [s for s in elf.syms if s["section"] == 0 and s["name"] and s["bind"] != 2]
            # __this_module is defined by the metadata translation unit below,
            # not an external provider imported by the linked source object.
            unresolved = [s["name"] for s in imports if s["name"] != "__this_module"
                          and s["name"] not in candidate_exports and s["name"] not in retained]
            assert not unresolved, "unresolved strong imports " + component + ": " + repr(unresolved)
            closure.append(dict(component=component, strong_imports=len(imports),
                                internal_imports={s["name"]: candidate_exports[s["name"]]["owner"] for s in imports if s["name"] in candidate_exports}))
        build.run([str(build.qb.context.CONTEXT/"scripts/mod/modpost"), "-e", "-a", "-i", str(args.output/"retained-dependencies.symvers"), "-o", str(args.output/"Module.symvers"), *linked], args.output, args.output/"joint-modpost")
        stderr = (args.output/"joint-modpost.stderr").read_text()
        assert not stderr.strip(), "modpost diagnostics " + stderr[-2000:]
        for component, _ in groups:
            folder = args.output/component
            cmd, _ = build.compile_command(component, component+".mod", folder, qsrc, wsrc, headers, True)
            build.run(cmd, build.qb.context.CONTEXT, folder/"compile-metadata")
            path = folder/(component+".ko")
            build.run([str(build.qb.context.TC)+"ld", "-r", "-z", "noexecstack", "--no-warn-rwx-segments", "--build-id=sha1", "-T", str(build.qb.context.CONTEXT/"scripts/module.lds"), "-o", str(path), str(folder/(component+".o")), str(folder/(component+".mod.o"))], folder, folder/"link-module")
            final = Elf(path)
            assert any(s["name"] == "__this_module" and s["section"] != 0 for s in final.syms), "missing generated module definition"
            unresolved = [s["name"] for s in final.syms if s["section"] == 0 and s["name"]
                          and s["bind"] != 2 and s["name"] not in candidate_exports and s["name"] not in retained]
            assert not unresolved, "final strong import unresolved " + repr(unresolved)
            result["modules"].append(dict(component=component, path=str(path), bytes=path.stat().st_size, sha256=sha(path)))
        for path, digest in pinmap.items():
            assert sha(path) == digest, "input drift after composition " + path
        result.update(status="PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS",
                      inputs_unchanged=True, complete_modules=7, retained_contract=receipt,
                      candidate_exports=len(candidate_exports), closure=closure,
                      modpost_diagnostics="empty", pins_verified=len(pinmap))
    except Exception as error:
        result["error"] = str(error)
    (args.output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    return int(not result["status"].startswith("PASS_"))


if __name__ == "__main__":
    raise SystemExit(main())
