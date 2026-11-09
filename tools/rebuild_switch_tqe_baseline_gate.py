"""Reconstruct exact switch_tqe baseline in new immutable offline output only.

This gate never patches an ELF, creates firmware, or interacts with hardware.
It uses retained ARC compiler commands and F363 generated ABI context. Any
reconstruction mismatch is a NO_GO; successful recompilation is not acceptance.
Run inside the existing REA-Linux distribution, not the Windows host compiler.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

import compile_f368_changed_objects as context
from qualify_f370_qdrv_module import Elf, baseline_compare

ROOT = context.ROOT
OLD = ROOT / "work/linux510-radio-port/quantenna/platform/topaz"
SOURCE = ROOT / "work/linux510-radio-port/quantenna-f344-peers/platform/topaz/switch_tqe.c"
PARENT = ROOT / "outputs/rea/arc700-20261021-r2/tqe-current/switch_tqe.ko"
SOURCE_SHA = "929d89801045c2b5f421d4d40ca312c32feaf93612de6a575b9b362ab97d9aef"
PARENT_SHA = "bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f"
PEER_SYMVERS = Path("/workspace/OpenMitraStar-build/f364/f364-lifetime-20260921T204704Z/dependencies.symvers")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: Path, log: Path) -> bytes:
    log.with_suffix(".command.json").write_text(json.dumps(command, indent=2) + "\n")
    proc = subprocess.run(command, cwd=cwd, capture_output=True, timeout=180)
    log.with_suffix(".stdout").write_bytes(proc.stdout)
    log.with_suffix(".stderr").write_bytes(proc.stderr)
    if proc.returncode:
        raise RuntimeError(f"{log.name}: exit {proc.returncode}: " + proc.stderr.decode(errors="replace")[-3000:])
    return proc.stdout


def command(name: str, folder: Path) -> list[str]:
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
    if name == "switch_tqe":
        result[-1] = str(SOURCE)
        # Retain exact __FILE__ identity without changing the source on disk.
        result.insert(result.index("-c"), "-ffile-prefix-map=" + str(SOURCE.parent) + "=" + str(OLD))
    else:
        result[-1] = str(folder / (name + ".c"))
    return result


def modinfo(module: Path) -> dict[str, list[str]]:
    values = {}
    for raw in Elf(module).byname[".modinfo"]["data"].split(b"\0"):
        if b"=" in raw:
            key, value = raw.decode().split("=", 1)
            values.setdefault(key, []).append(value)
    return {k: sorted(v) for k, v in values.items()}


def input_paths() -> list[Path]:
    paths = {SOURCE, OLD / "switch_tqe.c", PARENT, context.CONTEXT / ".config",
             context.CONTEXT / "Module.symvers", PEER_SYMVERS,
             context.CONTEXT / "include/generated/autoconf.h",
             context.CONTEXT / "scripts/mod/modpost", context.CONTEXT / "scripts/module.lds",
             OLD / ".switch_tqe.o.cmd", OLD / ".switch_tqe.mod.o.cmd", OLD / ".switch_tqe.ko.cmd",
             Path(__file__), ROOT / "tools/compile_f368_changed_objects.py",
             ROOT / "tools/qualify_f370_qdrv_module.py", ROOT / "tools/build_f370_qdrv_module.py"}
    # Retained dependency declarations let this gate pin used headers before
    # compilation, including recovered source headers and generated ABI files.
    for name in ("switch_tqe", "switch_tqe.mod"):
        for line in (OLD / ("." + name + ".o.cmd")).read_text().splitlines()[1:]:
            token = line.strip().removesuffix("\\").strip()
            if not token or token.startswith(("$", "deps_", "source_")) or ":" in token or " " in token:
                continue
            if token.startswith("/home/user/mitrastar-linux-5.10.260"):
                token = token.replace("/home/user/mitrastar-linux-5.10.260", str(context.KERNEL), 1)
            path = Path(token) if token.startswith("/") else context.CONTEXT / token
            if path.is_file():
                paths.add(path)
    for tool in ("gcc", "ld", "nm", "objcopy"):
        paths.add(Path(str(context.TC) + tool))
    for tree in ("include/generated", "arch/arc/include/generated", "include/config"):
        paths.update(path for path in (context.CONTEXT / tree).rglob("*") if path.is_file())
    return sorted(paths, key=str)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to((ROOT / "outputs/rea").resolve())
    if not out.name.startswith("driver5g-ops-"):
        raise ValueError("output name must start driver5g-ops-; existing evidence is never replaced")
    if out.exists():
        raise FileExistsError("immutable output already exists: " + str(out))
    assert sha(SOURCE) == SOURCE_SHA and sha(OLD / "switch_tqe.c") == SOURCE_SHA
    assert sha(PARENT) == PARENT_SHA and PARENT.stat().st_size == 35552
    for path in input_paths():
        assert path.is_file(), "missing required input: " + str(path)
    pins = {str(path): sha(path) for path in input_paths()}
    out.mkdir(parents=True, exist_ok=False)
    (out / "input-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    result = {"schema": "openmitrastar.switch-tqe-baseline-rebuild/v1",
              "status": "NO_GO_BASELINE_RECONSTRUCTION", "hardware_accessed": False,
              "firmware_image": False, "firmware_eligible": False,
              "physical_gates": "UNRUN", "source_sha256": SOURCE_SHA,
              "parent_module_sha256": PARENT_SHA, "modules": [],
              "limits": "Baseline reconstruction only. No arbitration fix, replacement policy, runtime, traffic, persistence or release acceptance."}
    try:
        dependencies = out / "dependencies.symvers"
        dependencies.write_text((context.CONTEXT / "Module.symvers").read_text() + PEER_SYMVERS.read_text())
        for lane in ("a", "b"):
            folder = out / lane
            folder.mkdir()
            run(command("switch_tqe", folder), context.CONTEXT, folder / "compile-source")
            deps = (folder / "switch_tqe.d").read_text().split(":", 1)[1].replace("\\\n", " ").split()
            missing = sorted({str((Path(dep) if dep.startswith("/") else context.CONTEXT / dep).resolve())
                              for dep in deps} - {str(Path(path).resolve()) for path in pins})
            assert not missing, "un-pinned compiler dependencies: " + str(missing)
            (folder / ".switch_tqe.o.cmd").write_text(
                "source_" + str(folder / "switch_tqe.o") + " := " + str(SOURCE) + "\n\n" +
                "deps_" + str(folder / "switch_tqe.o") + " := \\\n" +
                "".join("  " + path + " \\\n" for path in deps) + "\n")
            (folder / "switch_tqe.mod").write_text(str(folder / "switch_tqe.o") + "\n")
            # The retained parent has no srcversion; -a would add one and shift
            # every subsequent .modinfo symbol. Preserve its exact contract.
            run([str(context.CONTEXT / "scripts/mod/modpost"), "-e", "-i", str(dependencies),
                 "-o", str(folder / "Module.symvers"), str(folder / "switch_tqe.o")], folder, folder / "modpost")
            run(command("switch_tqe.mod", folder), context.CONTEXT, folder / "compile-metadata")
            run([str(context.TC) + "ld", "-r", "-z", "noexecstack", "--no-warn-rwx-segments",
                 "--build-id=sha1", "-T", str(context.CONTEXT / "scripts/module.lds"),
                 "-o", str(folder / "switch_tqe.ko"), str(folder / "switch_tqe.o"),
                 str(folder / "switch_tqe.mod.o")], folder, folder / "link-module")
            module = folder / "switch_tqe.ko"
            result["modules"].append({"lane": lane, "path": str(module), "bytes": module.stat().st_size, "sha256": sha(module)})
        assert sha(out / "a/switch_tqe.ko") == sha(out / "b/switch_tqe.ko"), "modules differ across independent compilations"
        comparison = baseline_compare(Elf(PARENT), Elf(out / "a/switch_tqe.ko"))
        (out / "full-baseline-comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
        old_info, new_info = modinfo(PARENT), modinfo(out / "a/switch_tqe.ko")
        metadata_errors = [key for key in set(old_info) | set(new_info) if old_info.get(key) != new_info.get(key)]
        (out / "metadata-comparison.json").write_text(json.dumps({"parent": old_info, "rebuild": new_info, "errors": metadata_errors}, indent=2) + "\n")
        result.update(reproducible=True, full_baseline_comparison_status=comparison["status"],
                      baseline_functions=comparison["function_count"], baseline_relocations=comparison["relocations_total"],
                      baseline_symbols=comparison["symbols_total"], baseline_code_bytes=comparison["code_allocated_bytes"],
                      metadata_errors=metadata_errors, comparison_errors=comparison["errors"])
        result["whole_file_exact"] = sha(out / "a/switch_tqe.ko") == PARENT_SHA
        for path, digest in pins.items():
            assert sha(Path(path)) == digest, "protected input changed: " + path
        result["protected_inputs_unchanged"] = True
        if not comparison["errors"] and not metadata_errors and result["whole_file_exact"]:
            result["status"] = "PASS_OFFLINE_FULL_BASELINE_EQUIVALENT"
    except Exception as exc:
        result["error"] = str(exc)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return int(result["status"] != "PASS_OFFLINE_FULL_BASELINE_EQUIVALENT")


if __name__ == "__main__":
    raise SystemExit(main())
