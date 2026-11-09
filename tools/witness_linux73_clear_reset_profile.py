"""Read-only actual Kbuild macro witness for the R26 clear/reset fixture.

Replays only preprocessing from the already-built qdrv_control command.
No kernel/module rebuild and no router access. Output must be new.
"""
import argparse
import ast
import hashlib
import json
import re
import shlex
import struct
import subprocess
from pathlib import Path

NAMES = (
    "HEADER_CORE_DUMP", "CONFIG_ARC_MUC_STACK_INIT", "CONFIG_ARC_MUC_STACK_SIZE",
    "RUBY_SRAM_BEGIN", "RUBY_SRAM_SIZE", "CONFIG_ARC_MUC_SRAM_B1_BASE",
    "CONFIG_ARC_MUC_SRAM_B1_SIZE", "CONFIG_ARC_MUC_SRAM_B2_BASE",
    "CONFIG_ARC_MUC_SRAM_B2_SIZE", "RUBY_CRUMBS_ADDR", "RUBY_CRUMBS_SIZE",
    "RUBY_DRAM_BEGIN", "RUBY_MAX_DRAM_SIZE", "CONFIG_ARC_MUC_BASE",
    "CONFIG_ARC_MUC_SIZE", "CONFIG_ARC_DSP_BASE", "CONFIG_ARC_DSP_SIZE",
    "TOPAZ_RX_ACCELERATE", "TOPAZ_MMAP_UNIFIED", "RUBY_MMAP_FLIP",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eval_integer(expression):
    expression = re.sub(r"\b(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]+\b", r"\1", expression)
    tree = ast.parse(expression, mode="eval")
    allowed = (ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub,
               ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.LShift, ast.RShift,
               ast.BitAnd, ast.BitOr, ast.BitXor, ast.Invert, ast.USub, ast.UAdd)
    assert all(isinstance(n, allowed) for n in ast.walk(tree)), expression
    # C profile ROUNDUP uses positive integer division. Preserve that semantic.
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            node.op = ast.FloorDiv()
    ast.fix_missing_locations(tree)
    return int(eval(compile(tree, "<preprocessed-profile>", "eval"), {"__builtins__": {}}, {}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    a.output.mkdir(parents=True)
    source = a.candidate / "source/qdrv/qdrv_control.c"
    command_file = a.build / "source/qdrv/.qdrv_control.o.cmd"
    raw = command_file.read_text().splitlines()[0].split(":=", 1)[1].strip()
    original = shlex.split(raw)
    command = []
    i = 0
    while i < len(original):
        arg = original[i]
        if arg == "-o":
            i += 2
            continue
        if arg == "-c" or arg.startswith("-Wp,-MMD,") or arg == "source/qdrv/qdrv_control.c":
            i += 1
            continue
        command.append(arg)
        i += 1
    probe = a.output / "actual-profile.c"
    probe.write_text('#include "' + source.as_posix() + '"\n' + "\n".join(
        f"OM73_PROFILE_{name} = ({name});" for name in NAMES) + "\n")
    pp = subprocess.run(command + ["-E", "-P", str(probe)], cwd=a.build, capture_output=True)
    (a.output / "preprocess.log").write_bytes(pp.stderr)
    assert not pp.returncode, pp.stderr.decode(errors="replace")
    selected = "\n".join(line for line in pp.stdout.decode().splitlines()
                         if line.startswith("OM73_PROFILE_"))
    (a.output / "actual-profile-expanded.txt").write_text(selected + "\n")
    values = {}
    for line in selected.splitlines():
        match = re.fullmatch(r"OM73_PROFILE_(\w+) = (.*);", line)
        assert match, line
        values[match[1]] = eval_integer(match[2])
    assert set(values) == set(NAMES)
    # Independently corroborate evaluator values with actual ARC compiler data.
    compiled_probe = a.output / "actual-profile-values.c"
    expressions = [re.fullmatch(r"OM73_PROFILE_(\w+) = (.*);", line)[2]
                   for line in selected.splitlines()]
    compiled_probe.write_text("const unsigned int om73_profile_values[] = {\n" +
                              ",\n".join(expressions) + "\n};\n")
    obj = a.output / "actual-profile-values.o"
    cc = subprocess.run([command[0], "-mcpu=arc700", "-std=gnu11", "-c",
                         str(compiled_probe), "-o", str(obj)], capture_output=True)
    (a.output / "profile-values-compile.log").write_bytes(cc.stdout + cc.stderr)
    assert not cc.returncode, cc.stderr.decode(errors="replace")
    objcopy = Path(command[0]).with_name(Path(command[0]).name.replace("gcc", "objcopy"))
    data = a.output / "actual-profile-values.bin"
    dump = subprocess.run([str(objcopy), "--dump-section", f".rodata={data}", str(obj)],
                          capture_output=True)
    assert not dump.returncode, dump.stderr.decode(errors="replace")
    assert len(data.read_bytes()) == len(NAMES) * 4
    compiled_values = dict(zip(NAMES, struct.unpack("<" + "I" * len(NAMES), data.read_bytes())))
    assert compiled_values == values, (compiled_values, values)
    dm = subprocess.run(command + ["-E", "-dM", str(source)], cwd=a.build, capture_output=True)
    assert not dm.returncode, dm.stderr.decode(errors="replace")
    macros = a.output / "actual-kbuild-macros.txt"
    macros.write_bytes(dm.stdout)
    (a.output / "preprocess-command.json").write_text(json.dumps({
        "cwd": str(a.build), "original": original,
        "preprocess": command + ["-E", "-P", str(probe)],
    }, indent=2) + "\n")
    result = {
        "status": "PASS_R26_SOURCE_ACTUAL_R24_KBUILD_MACRO_PROFILE_WITNESS",
        "hardware_accessed": False, "firmware_eligible": False,
        "constants": values,
        "arc_compiler_constant_values_verified": True,
        "regions": {
            "muc-stack": {"start": values["CONFIG_ARC_MUC_STACK_INIT"] - values["CONFIG_ARC_MUC_STACK_SIZE"],
                          "size": values["CONFIG_ARC_MUC_STACK_SIZE"]},
            "muc-sram-b1": {"start": values["RUBY_SRAM_BEGIN"] + values["CONFIG_ARC_MUC_SRAM_B1_BASE"],
                            "size": values["CONFIG_ARC_MUC_SRAM_B1_SIZE"]},
            "muc-sram-b2": {"start": values["RUBY_SRAM_BEGIN"] + values["CONFIG_ARC_MUC_SRAM_B2_BASE"],
                            "size": values["CONFIG_ARC_MUC_SRAM_B2_SIZE"]},
            "crumbs": {"start": values["RUBY_CRUMBS_ADDR"], "size": values["RUBY_CRUMBS_SIZE"]},
            "muc-dram": {"start": values["RUBY_DRAM_BEGIN"] + values["CONFIG_ARC_MUC_BASE"],
                         "size": values["CONFIG_ARC_MUC_SIZE"]},
            "dsp-dram": {"start": values["RUBY_DRAM_BEGIN"] + values["CONFIG_ARC_DSP_BASE"],
                         "size": values["CONFIG_ARC_DSP_SIZE"]},
        },
        "maximum_crash_log_bytes": values["CONFIG_ARC_MUC_STACK_SIZE"] - 4,
        "pins": {str(path): digest(path) for path in (
            Path(__file__), source, command_file, probe, macros,
            a.output / "actual-profile-expanded.txt", compiled_probe, obj, data,
            Path(command[0]), objcopy)},
        "limits": ["Actual R26 qdrv_control source preprocessed using R24 successful native Kbuild command.",
                   "MMIO access, producer quiescence, hardware and firmware execution are untested."]
    }
    (a.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
