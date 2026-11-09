"""Compile/link the isolated two-alias WLAN candidate twice; no hardware or ELF patch.

Uses all nineteen complete, pinned, source-built objects from a qualified WLAN
baseline build. Only the changed source unit is compiled again for each lane.
This is a full linked candidate module, pending an independent whole-delta audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

import compile_f368_changed_objects as context
from qualify_f370_qdrv_module import Elf

ROOT = context.ROOT
OLD = ROOT / "work/linux510-radio-port/quantenna/wlan"
SOURCE_SHA = "3bed348b48ae1da8a671a5ff1bb4f919fd773bf06c3d53fd130b5a4247433d96"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, log):
    log.with_suffix(".command.json").write_text(json.dumps(command, indent=2) + "\n")
    process = subprocess.run(command, cwd=cwd, capture_output=True, timeout=180)
    log.with_suffix(".stdout").write_bytes(process.stdout)
    log.with_suffix(".stderr").write_bytes(process.stderr)
    if process.returncode:
        raise RuntimeError(log.name + ": " + process.stderr.decode(errors="replace")[-2500:])


def command(name, folder, source):
    original = shlex.split((OLD / ("." + name + ".o.cmd")).read_text().splitlines()[0].split(" := ", 1)[1])
    result = []
    for arg in original:
        arg = arg.replace("/home/user/mitrastar-linux-5.10.260", str(context.KERNEL))
        if arg in ("-I./arch/arc/include/generated", "-I./include", "-I./arch/arc/include/generated/uapi", "-I./include/generated/uapi"):
            arg = "-I" + str(context.CONTEXT / arg[4:])
        if arg.startswith("-Wp,-MMD,"):
            arg = "-Wp,-MMD," + str(folder / (name + ".d"))
        result.append(arg)
    result[result.index("-o") + 1] = str(folder / (name + ".o"))
    result[-1] = str(folder / (name + ".c") if name == "wlan.mod" else source)
    if name != "wlan.mod":
        result.insert(result.index("-c"), "-ffile-prefix-map=" + str(source.parent) + "=" + str(OLD))
        result.insert(result.index("-c"), "-I" + str(OLD))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-build", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to((ROOT / "outputs/rea").resolve())
    assert output.name.startswith("driver5g-ops-") and not output.exists()
    assert sha(args.source) == SOURCE_SHA, "candidate source changed"
    proof = json.loads((args.baseline_build / "result.json").read_text())
    assert proof["status"] in ("PASS_OFFLINE_FULL_BASELINE_BYTE_IDENTICAL", "PASS_OFFLINE_FULL_BASELINE_EQUIVALENT_DECLARED_SRCVERSION")
    assert proof["protected_inputs_unchanged"] and proof["reproducible"] and not proof["comparison_errors"]
    pins = json.loads((args.baseline_build / "input-pins.json").read_text())
    for path, digest in pins.items():
        assert sha(path) == digest, "baseline inputs changed: " + path
    names = proof["units"]
    assert len(names) == 19 and "ieee80211_wireless" in names
    for lane in ("a", "b"):
        assert sha(args.baseline_build / lane / "wlan.ko") == proof["modules"][0]["sha256"]
        for name in names:
            path = args.baseline_build / lane / (name + ".o")
            pins[str(path)] = sha(path)
    for path in (Path(__file__), args.source, args.source.parent / "result.json",
                 args.baseline_build / "result.json", args.baseline_build / "input-pins.json",
                 args.baseline_build / "dependencies.symvers"):
        pins[str(path)] = sha(path)
    output.mkdir(parents=True, exist_ok=False)
    (output / "input-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    canonical_pins = {str(Path(path).resolve()) for path in pins}
    canonical_dependencies = {}
    def dependency_path(dep):
        if dep not in canonical_dependencies:
            canonical_dependencies[dep] = str((Path(dep) if dep.startswith("/") else context.CONTEXT / dep).resolve())
        return canonical_dependencies[dep]
    result = {"schema": "openmitrastar.wlan-txmaxmpdu-alias-module/v1", "status": "NO_GO_MODULE_BUILD",
              "hardware_accessed": False, "firmware_image": False, "firmware_eligible": False,
              "physical_gates": "UNRUN", "modules": [], "changed_source": str(args.source),
              "baseline_build": str(args.baseline_build), "limits": "Full source-built module linkage; whole module table/code/data/relocation delta qualification pending."}
    try:
        for lane in ("a", "b"):
            folder = output / lane
            folder.mkdir()
            run(command("ieee80211_wireless", folder, args.source), context.CONTEXT, folder / "compile-changed-source")
            for name in names:
                deps = ((folder / (name + ".d")) if name == "ieee80211_wireless" else (args.baseline_build / lane / (name + ".d"))).read_text().split(":", 1)[1].replace("\\\n", " ").split()
                missing = sorted({dependency_path(dep) for dep in deps} - canonical_pins)
                assert not missing, "un-pinned dependencies: " + str(missing)
                if name != "ieee80211_wireless":
                    # Copy immutable baseline objects as bytes, never rewriting
                    # their retained source/build evidence or patching the ELF.
                    (folder / (name + ".o")).write_bytes((args.baseline_build / lane / (name + ".o")).read_bytes())
                (folder / ("." + name + ".o.cmd")).write_text(
                    "source_" + str(folder / (name + ".o")) + " := " + str(args.source if name == "ieee80211_wireless" else OLD / (name + ".c")) + "\n\n" +
                    "deps_" + str(folder / (name + ".o")) + " := \\\n" + "".join("  " + dep + " \\\n" for dep in deps) + "\n")
            objects = [str(folder / (name + ".o")) for name in names]
            (folder / "wlan.mod").write_text("\n".join(objects) + "\n")
            run([str(context.TC) + "ld", "-z", "noexecstack", "--no-warn-rwx-segments", "-r", "-o", str(folder / "wlan.o"), *objects], folder, folder / "link-relocatable")
            run([str(context.CONTEXT / "scripts/mod/modpost"), "-e", "-a", "-i", str(args.baseline_build / "dependencies.symvers"), "-o", str(folder / "Module.symvers"), str(folder / "wlan.o")], folder, folder / "modpost")
            run(command("wlan.mod", folder, args.source), context.CONTEXT, folder / "compile-metadata")
            run([str(context.TC) + "ld", "-r", "-z", "noexecstack", "--no-warn-rwx-segments", "--build-id=sha1", "-T", str(context.CONTEXT / "scripts/module.lds"), "-o", str(folder / "wlan.ko"), str(folder / "wlan.o"), str(folder / "wlan.mod.o")], folder, folder / "link-module")
            module = folder / "wlan.ko"
            result["modules"].append({"lane": lane, "path": str(module), "bytes": module.stat().st_size, "sha256": sha(module)})
        assert sha(output / "a/wlan.ko") == sha(output / "b/wlan.ko"), "candidate compilations differ"
        for path, digest in pins.items():
            assert sha(path) == digest, "protected input changed: " + path
        elf = Elf(output / "a/wlan.ko")
        result.update(status="PASS_FULL_LINKED_MODULE_PENDING_DELTA_QUALIFICATION", reproducible=True,
                      baseline_compiled_units_reused=18, changed_source_units_compiled_per_lane=1,
                      all_nineteen_source_built_units_linked=True, protected_inputs_unchanged=True,
                      functions=sum(sym["type"] == 2 and sym["size"] > 0 for sym in elf.syms),
                      relocations=len(elf.relas), symbols=len(elf.syms))
    except Exception as exc:
        result["error"] = str(exc)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return int(result["status"] != "PASS_FULL_LINKED_MODULE_PENDING_DELTA_QUALIFICATION")


if __name__ == "__main__":
    raise SystemExit(main())
