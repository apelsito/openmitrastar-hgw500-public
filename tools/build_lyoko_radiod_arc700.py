#!/usr/bin/env python3
"""Build the portable lyoko-radiod policy engine for ARC700."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/userland/lyoko-radiod"
OUT = ROOT / "outputs/userland/lyoko-radiod-arc700-20260905"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
TOOLCHAIN = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
EXPECTED_PROFILE = SOURCE / "profiles/hgw500bna-qcv2.profile"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_wsl(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    if OUT.exists():
        if not args.replace_existing:
            raise SystemExit(f"refusing to overwrite evidence directory: {OUT}")
        if OUT.resolve().parent != (ROOT / "outputs/userland").resolve():
            raise SystemExit(f"unsafe output path: {OUT}")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    source_wsl = f"{WS_ROOT}/{SOURCE.relative_to(ROOT).as_posix()}"
    out_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"
    script = f"""
set -eu
src={shlex.quote(source_wsl)}
out={shlex.quote(out_wsl)}
tc={shlex.quote(TOOLCHAIN)}
build_one() {{
    target="$1"
    "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror \
        -ffunction-sections -fdata-sections -fno-ident \
        -I"$src/include" "$src/src/core.c" "$src/src/journal.c" \
        "$src/src/profile.c" "$src/src/file_backend.c" "$src/src/main.c" -static \
        -Wl,--gc-sections -Wl,--build-id=none -o "$target"
    "${{tc}}strip" "$target"
}}
build_one "$out/lyoko-radiod.a"
build_one "$out/lyoko-radiod.b"
cmp "$out/lyoko-radiod.a" "$out/lyoko-radiod.b"
mv "$out/lyoko-radiod.a" "$out/lyoko-radiod"
rm "$out/lyoko-radiod.b"
file "$out/lyoko-radiod" >"$out/file.txt"
"${{tc}}readelf" -h "$out/lyoko-radiod" >"$out/readelf.txt"
"${{tc}}readelf" -d "$out/lyoko-radiod" >"$out/dynamic.txt" 2>&1 || true
"${{tc}}nm" -u "$out/lyoko-radiod" >"$out/undefined.txt"
test ! -s "$out/undefined.txt"
grep -q 'statically linked' "$out/file.txt"
grep -q 'Machine:.*ARCompact' "$out/readelf.txt"
grep -q 'ARC700' "$out/readelf.txt"
grep -q 'There is no dynamic section' "$out/dynamic.txt"
"""
    result = run_wsl(script)
    (OUT / "build.stdout.log").write_text(result.stdout, encoding="utf-8")
    (OUT / "build.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)

    binary = OUT / "lyoko-radiod"
    sources = sorted(path for path in SOURCE.rglob("*") if path.is_file())
    manifest = {
        "schema": "lyoko.radiod-arc700-build/v1",
        "date": "2026-09-05",
        "status": "PASS",
        "target": "ARC700 Linux uClibc",
        "binary": {
            "file": binary.name,
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "static": True,
            "undefined_symbols": 0,
            "reproducible_two_builds": True,
        },
        "policy": {
            "hysteresis_percent": 15,
            "stability_seconds": 1800,
            "active_window": "04:00-04:04",
            "high_frequency_state": "RAM",
            "persistent_commit_limit": "one per local day",
            "persistence_backend": "abstract; no MTD access in this artifact",
        },
        "board_profile": {
            "file": EXPECTED_PROFILE.relative_to(ROOT).as_posix(),
            "sha256": sha256(EXPECTED_PROFILE),
        },
        "sources": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sources
        ],
        "hardware_actions": {
            "router": False,
            "uart": False,
            "ssh": False,
            "flash": False,
            "mtd": False,
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
