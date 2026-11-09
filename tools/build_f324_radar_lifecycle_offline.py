"""Build the F324 transaction core/model only; never build or flash firmware."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f324_radar_lifecycle"
COMPILER = ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-gcc"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux(path: Path) -> str:
    path = path.resolve()
    if not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise ValueError("expected a local Windows drive")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "outputs/kernel-port" / ("f324-radar-lifecycle-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    for name in ("f324_lifecycle.c", "f324_lifecycle.h", "test_f324_lifecycle.c"):
        (out / name).write_bytes((SOURCE / name).read_bytes())
    source = shlex.quote(linux(out))
    cc = shlex.quote(linux(COMPILER))
    tc = shlex.quote(linux(COMPILER)[:-3])
    script = f"""set -eu
out={source}
cc={cc}
tc={tc}
cc --version >"$out/host-compiler.txt"
"$cc" --version >"$out/arc-compiler.txt"
cc -std=c99 -O2 -g -Wall -Wextra -Werror -pedantic \\
    "$out/f324_lifecycle.c" "$out/test_f324_lifecycle.c" -o "$out/test-f324"
"$out/test-f324" >"$out/model-tests.log" 2>&1
for name in a b; do
    "$cc" -std=c99 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-common \\
        -mlong-calls -c "$out/f324_lifecycle.c" -o "$out/f324-$name.o"
done
cmp "$out/f324-a.o" "$out/f324-b.o"
"${{tc}}ar" rcsD "$out/libf324radar-lifecycle.a" "$out/f324-a.o"
"${{tc}}readelf" -h "$out/f324-a.o" >"$out/arc-readelf.txt"
"${{tc}}nm" -u "$out/f324-a.o" >"$out/arc-undefined.txt"
"${{tc}}objdump" -dr "$out/f324-a.o" >"$out/arc-disassembly.txt"
"""
    (out / "build.sh").write_bytes(script.encode("utf-8"))
    proc = subprocess.run(
        ["wsl.exe", "-d", args.distro, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-s"],
        input=script.encode("utf-8"), capture_output=True, timeout=120, check=False,
    )
    (out / "build.stdout.txt").write_bytes(proc.stdout)
    (out / "build.stderr.txt").write_bytes(proc.stderr)
    if proc.returncode:
        print(json.dumps({"status": "OFFLINE_BUILD_FAILED", "report_directory": str(out),
                          "returncode": proc.returncode, "hardware_actions": False}))
        return 1
    model = (out / "model-tests.log").read_text().strip()
    match = re.fullmatch(r"F324_LIFECYCLE_MODEL_PASS cases=(\d+) hardware_backend=absent physical_pass=0", model)
    if not match or "ARC" not in (out / "arc-readelf.txt").read_text():
        raise ValueError("model result or target architecture is not established")
    if (out / "arc-undefined.txt").read_text().strip():
        raise ValueError("unexpected external dependencies in the portable core")
    artifact = out / "libf324radar-lifecycle.a"
    result = {
        "schema": "openmitrastar.f324-radar-lifecycle-core/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_OFFLINE_TRANSACTION_MODEL_NO_GO_FIRMWARE",
        "tests": {"cases": int(match[1]), "asan": False, "ubsan": False,
                  "scope": "stateful simulated producer, partial failures, checkpoint retention, no unsafe release"},
        "artifact": {"path": str(artifact), "bytes": artifact.stat().st_size, "sha256": digest(artifact),
                     "kind": "ARC700 static library; not a loadable module or flash image"},
        "reproducibility": {"two_object_builds_equal": digest(out / "f324-a.o") == digest(out / "f324-b.o")},
        "sources": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
                    for path in sorted(SOURCE.glob("*")) if path.is_file()],
        "compiler_sha256": digest(COMPILER),
        "hardware_adapter": "NOT_IMPLEMENTED_NO_VERIFIED_QT4_QUIESCE_AND_RESTORE_PRIMITIVE",
        "physical_detection_proven": False,
        "firmware_candidate_created": False,
        "flash_go_no_go": "NO_GO_MISSING_HARDWARE_PRIMITIVE_NOT_MISSING_OWNER_GO",
        "hardware_actions": {"router": False, "uart": False, "radio": False, "flash": False},
    }
    (out / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    (out / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.name}\n" for p in sorted(out.iterdir())
                                             if p.is_file() and p.name != "SHA256SUMS"), encoding="ascii")
    print(json.dumps({"status": result["status"], "tests": result["tests"],
                      "artifact": result["artifact"], "manifest": str(out / "manifest.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
