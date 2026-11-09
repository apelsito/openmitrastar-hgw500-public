"""Compile every F365 WLAN unit twice in immutable offline output; never hardware.

This is a full-source compile/link gate, not ELF patching or a firmware builder.
Retained ARC commands, generated ABI context, dependencies and all used headers
are pinned. The exact whole-file hash and complete metadata must match the parent.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from qualify_f370_qdrv_module import Elf, baseline_compare

ORIGINAL_ROOT = Path("/workspace/user-home/Desktop/MitraStar")
ORIGINAL_KERNEL = "/home/user/mitrastar-linux-5.10.260"
PARENT_SHA = "f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, log):
    log.with_suffix(".command.json").write_text(json.dumps(command, indent=2) + "\n")
    proc = subprocess.run(command, cwd=cwd, capture_output=True, timeout=180)
    log.with_suffix(".stdout").write_bytes(proc.stdout)
    log.with_suffix(".stderr").write_bytes(proc.stderr)
    if proc.returncode:
        raise RuntimeError(f"{log.name}: exit {proc.returncode}: " + proc.stderr.decode(errors="replace")[-2500:])
    return proc.stdout


def metadata(module):
    info = {}
    for raw in Elf(module).byname[".modinfo"]["data"].split(b"\0"):
        if b"=" in raw:
            key, value = raw.decode().split("=", 1)
            info.setdefault(key, []).append(value)
    return {key: sorted(value) for key, value in info.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ORIGINAL_ROOT)
    parser.add_argument("--kernel", type=Path, default=Path("/home/rea/openmitrastar-f368-build-20261021/linux-5.10.260"))
    parser.add_argument("--context", type=Path, default=Path("/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z/kernel"))
    parser.add_argument("--peer-symvers", type=Path, default=Path("/workspace/OpenMitraStar-build/f364/f364-lifetime-20260921T204704Z/dependencies.symvers"))
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--allow-declared-srcversion-delta", action="store_true",
                        help="Accept source identity metadata delta only after full code/data/symbol/relocation equivalence; never byte-identical status")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    old = root / "work/linux510-radio-port/quantenna/wlan"
    parent = args.parent or root / "outputs/rea/arc700-20261021-r2/f365-ram-activation/r3/payload/modules/wlan.ko"
    tc = root / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-"
    out = args.output.resolve()
    out.relative_to((root / "outputs/rea").resolve())
    if not out.name.startswith("driver5g-ops-") or out.exists():
        raise ValueError("new driver5g-ops- output required; existing evidence is never replaced")
    assert sha(parent) == PARENT_SHA and parent.stat().st_size == 629180
    names = [Path(value).stem for value in shlex.split((old / ".wlan.o.cmd").read_text().splitlines()[0].split(" := ", 1)[1]) if value.endswith(".o")][1:]
    assert len(names) == 19 and len(set(names)) == 19, "retained link object list"
    protected = {parent, old / "wlan.ko", old / "Makefile", old / ".wlan.o.cmd", old / ".wlan.mod.o.cmd",
                 old / ".wlan.ko.cmd", args.context / ".config", args.context / "Module.symvers",
                 args.peer_symvers, args.context / "scripts/mod/modpost", args.context / "scripts/module.lds",
                 Path(__file__), root / "tools/qualify_f370_qdrv_module.py"}
    for tool in ("gcc", "ld", "nm", "objcopy"):
        protected.add(Path(str(tc) + tool))
    for tree in ("include/generated", "arch/arc/include/generated", "include/config"):
        protected.update(path for path in (args.context / tree).rglob("*") if path.is_file())

    def mapped(value):
        return value.replace(str(ORIGINAL_ROOT), str(root)).replace(ORIGINAL_KERNEL, str(args.kernel))

    for name in names + ["wlan.mod"]:
        cmdfile = old / ("." + name + ".o.cmd")
        protected.add(cmdfile)
        if name != "wlan.mod":
            protected.add(old / (name + ".c"))
        for line in cmdfile.read_text().splitlines()[1:]:
            token = line.strip().removesuffix("\\").strip()
            if not token or token.startswith(("$", "deps_", "source_")) or ":" in token or " " in token:
                continue
            token = mapped(token)
            path = Path(token) if token.startswith("/") else args.context / token
            if path.is_file():
                protected.add(path)
    for path in protected:
        assert path.is_file(), "required input missing: " + str(path)
    pins = {str(path): sha(path) for path in sorted(protected, key=str)}
    out.mkdir(parents=True, exist_ok=False)
    (out / "input-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    result = {"schema": "openmitrastar.wlan-baseline-rebuild/v1", "status": "NO_GO_BASELINE_RECONSTRUCTION",
              "hardware_accessed": False, "firmware_image": False, "firmware_eligible": False,
              "physical_gates": "UNRUN", "parent_module_sha256": PARENT_SHA, "units": names, "modules": [],
              "limits": "Baseline-only rebuild. No feature enablement, runtime, client traffic, persistence or release acceptance."}
    try:
        dependencies = out / "dependencies.symvers"
        dependencies.write_text((args.context / "Module.symvers").read_text() + args.peer_symvers.read_text())
        def command(name, folder):
            original = shlex.split((old / ("." + name + ".o.cmd")).read_text().splitlines()[0].split(" := ", 1)[1])
            cmd = []
            for value in original:
                value = mapped(value)
                if value in ("-I./arch/arc/include/generated", "-I./include", "-I./arch/arc/include/generated/uapi", "-I./include/generated/uapi"):
                    value = "-I" + str(args.context / value[4:])
                if value.startswith("-Wp,-MMD,"):
                    value = "-Wp,-MMD," + str(folder / (name + ".d"))
                cmd.append(value)
            cmd[cmd.index("-o") + 1] = str(folder / (name + ".o"))
            cmd[-1] = str((folder if name == "wlan.mod" else old) / (name + ".c"))
            if name != "wlan.mod" and root != ORIGINAL_ROOT:
                cmd.insert(cmd.index("-c"), "-ffile-prefix-map=" + str(root) + "=" + str(ORIGINAL_ROOT))
            return cmd
        for lane in ("a", "b"):
            folder = out / lane
            folder.mkdir()
            def unit(name):
                run(command(name, folder), args.context, folder / name)
                deps = (folder / (name + ".d")).read_text().split(":", 1)[1].replace("\\\n", " ").split()
                missing = sorted({str((Path(dep) if dep.startswith("/") else args.context / dep).resolve())
                                  for dep in deps} - {str(Path(path).resolve()) for path in pins})
                assert not missing, "un-pinned compiler dependencies: " + str(missing)
                (folder / ("." + name + ".o.cmd")).write_text(
                    "source_" + str(folder / (name + ".o")) + " := " + str(old / (name + ".c")) + "\n\n" +
                    "deps_" + str(folder / (name + ".o")) + " := \\\n" + "".join("  " + p + " \\\n" for p in deps) + "\n")
                return name
            with ThreadPoolExecutor(max_workers=4) as pool:
                for name in pool.map(unit, names):
                    print(json.dumps({"lane": lane, "compiled": name}), flush=True)
            objects = [str(folder / (name + ".o")) for name in names]
            (folder / "wlan.mod").write_text("\n".join(objects) + "\n")
            run([str(tc) + "ld", "-z", "noexecstack", "--no-warn-rwx-segments", "-r", "-o", str(folder / "wlan.o"), *objects], folder, folder / "link-relocatable")
            # Parent has a srcversion and the original complete retained command
            # dependency declarations are restored for modpost generation.
            run([str(args.context / "scripts/mod/modpost"), "-e", "-a", "-i", str(dependencies), "-o", str(folder / "Module.symvers"), str(folder / "wlan.o")], folder, folder / "modpost")
            run(command("wlan.mod", folder), args.context, folder / "compile-metadata")
            run([str(tc) + "ld", "-r", "-z", "noexecstack", "--no-warn-rwx-segments", "--build-id=sha1",
                 "-T", str(args.context / "scripts/module.lds"), "-o", str(folder / "wlan.ko"), str(folder / "wlan.o"), str(folder / "wlan.mod.o")], folder, folder / "link-module")
            module = folder / "wlan.ko"
            result["modules"].append({"lane": lane, "path": str(module), "bytes": module.stat().st_size, "sha256": sha(module)})
        assert sha(out / "a/wlan.ko") == sha(out / "b/wlan.ko"), "candidate compilations differ"
        comparison = baseline_compare(Elf(parent), Elf(out / "a/wlan.ko"))
        (out / "full-baseline-comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
        parent_metadata, rebuilt_metadata = metadata(parent), metadata(out / "a/wlan.ko")
        (out / "metadata-comparison.json").write_text(json.dumps({"parent": parent_metadata, "rebuilt": rebuilt_metadata}, indent=2) + "\n")
        result.update(reproducible=True, full_baseline_comparison_status=comparison["status"],
                      comparison_errors=comparison["errors"], baseline_functions=comparison["function_count"],
                      baseline_relocations=comparison["relocations_total"], baseline_symbols=comparison["symbols_total"],
                      baseline_code_bytes=comparison["code_allocated_bytes"], metadata_exact=parent_metadata == rebuilt_metadata,
                      whole_file_exact=sha(out / "a/wlan.ko") == PARENT_SHA)
        metadata_delta = sorted(key for key in set(parent_metadata) | set(rebuilt_metadata)
                                if parent_metadata.get(key) != rebuilt_metadata.get(key))
        result["metadata_delta"] = metadata_delta
        result["declared_srcversion_delta_allowed"] = args.allow_declared_srcversion_delta
        for path, digest in pins.items():
            assert sha(path) == digest, "protected input changed: " + path
        result["protected_inputs_unchanged"] = True
        if not comparison["errors"] and result["metadata_exact"] and result["whole_file_exact"]:
            result["status"] = "PASS_OFFLINE_FULL_BASELINE_BYTE_IDENTICAL"
        elif (not comparison["errors"] and args.allow_declared_srcversion_delta
              and metadata_delta == ["srcversion"]):
            result["status"] = "PASS_OFFLINE_FULL_BASELINE_EQUIVALENT_DECLARED_SRCVERSION"
            result["limits"] += " Exact original source identity hash not reproduced: srcversion depends on recovered headers. No original metadata copied or ELF bytes patched."
    except Exception as exc:
        result["error"] = str(exc)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return int(not result["status"].startswith("PASS_OFFLINE_FULL_BASELINE_"))


if __name__ == "__main__":
    raise SystemExit(main())
