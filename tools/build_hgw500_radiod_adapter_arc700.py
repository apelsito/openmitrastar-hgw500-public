#!/usr/bin/env python3
"""Build the HGW-500BNA-QCv2 metrics adapter for ARC700."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/userland/lyoko-radiod/adapters/hgw500bna-qcv2"
OUT = ROOT / "outputs/userland/hgw500-radiod-adapter-arc700-20260905"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
TOOLCHAIN = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "$src/hgw500_adapter.c" -static -Wl,--gc-sections \
        -Wl,--build-id=none -o "$target"
    "${{tc}}strip" "$target"
}}
build_one "$out/hgw500-radiod-adapter.a"
build_one "$out/hgw500-radiod-adapter.b"
cmp "$out/hgw500-radiod-adapter.a" "$out/hgw500-radiod-adapter.b"
mv "$out/hgw500-radiod-adapter.a" "$out/hgw500-radiod-adapter"
rm "$out/hgw500-radiod-adapter.b"
file "$out/hgw500-radiod-adapter" >"$out/file.txt"
"${{tc}}readelf" -h "$out/hgw500-radiod-adapter" >"$out/readelf.txt"
"${{tc}}readelf" -d "$out/hgw500-radiod-adapter" >"$out/dynamic.txt" 2>&1 || true
"${{tc}}nm" -u "$out/hgw500-radiod-adapter" >"$out/undefined.txt"
test ! -s "$out/undefined.txt"
grep -q 'statically linked' "$out/file.txt"
grep -q 'Machine:.*ARCompact' "$out/readelf.txt"
grep -q 'ARC700' "$out/readelf.txt"
grep -q 'There is no dynamic section' "$out/dynamic.txt"
"""
    result = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
        check=False,
    )
    (OUT / "build.stdout.log").write_text(result.stdout, encoding="utf-8")
    (OUT / "build.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    binary = OUT / "hgw500-radiod-adapter"
    manifest = {
        "schema": "lyoko.hgw500-radiod-adapter-arc700/v1",
        "date": "2026-09-05",
        "status": "PASS",
        "binary": {
            "file": binary.name,
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "static": True,
            "undefined_symbols": 0,
            "reproducible_two_builds": True,
        },
        "contract": {
            "snapshot_only": True,
            "command_execution": False,
            "network": False,
            "writes": False,
            "mac_output": False,
            "ssid_output": False,
            "psk_output": False,
        },
        "source": {
            "path": (SOURCE / "hgw500_adapter.c").relative_to(ROOT).as_posix(),
            "sha256": sha256(SOURCE / "hgw500_adapter.c"),
        },
        "hardware_actions": {"router": False, "uart": False, "ssh": False, "mtd": False},
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
