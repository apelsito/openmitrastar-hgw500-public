#!/usr/bin/env python3
"""Build the unified portable F316 radar classifier for ARC700."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f316_radar_classifier"
OUT = ROOT / "outputs/kernel-port/f316-radar-classifier-20260905"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
TOOLCHAIN = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"


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
        if OUT.resolve().parent != (ROOT / "outputs/kernel-port").resolve():
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
make -C "$src" clean test >"$out/host-tests.log" 2>&1
build_one() {{
    target="$1"
    dir=$(dirname "$target")
    mkdir -p "$dir"
    "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
        -I"$src" -I"$src/preprocess" -I"$src/ssr_itlv" -I"$src/lsr" -I"$src/postfilter" -I"$src/candidate_selector" \
        -c "$src/f316_classifier.c" -o "$dir/classifier.o"
    "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -I"$src/preprocess" \
        -c "$src/preprocess/f316_preprocess.c" -o "$dir/preprocess.o"
    "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -I"$src/ssr_itlv" \
        -c "$src/ssr_itlv/f316_ssr_itlv.c" -o "$dir/ssr_itlv.o"
    "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -I"$src/lsr" \
        -c "$src/lsr/f316_lsr.c" -o "$dir/lsr.o"
    "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -I"$src/postfilter" \
        -c "$src/postfilter/f316_postfilter.c" -o "$dir/postfilter.o"
    "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -I"$src/candidate_selector" \
        -c "$src/candidate_selector/f316_candidate_selector.c" -o "$dir/candidate_selector.o"
    "${{tc}}ar" rcsD "$target" "$dir/classifier.o" "$dir/preprocess.o" "$dir/ssr_itlv.o" "$dir/lsr.o" "$dir/postfilter.o" "$dir/candidate_selector.o"
}}
build_one /tmp/f316-a/libf316radar.a
build_one /tmp/f316-b/libf316radar.a
cmp /tmp/f316-a/libf316radar.a /tmp/f316-b/libf316radar.a
cp /tmp/f316-a/libf316radar.a "$out/libf316radar.a"
"${{tc}}nm" -u "$out/libf316radar.a" >"$out/undefined.txt"
"${{tc}}size" "$out/libf316radar.a" >"$out/size.txt"
"${{tc}}readelf" -h /tmp/f316-a/classifier.o >"$out/readelf.txt"
grep -q 'Machine:.*ARCompact' "$out/readelf.txt"
"""
    result = run_wsl(script)
    (OUT / "build.stdout.log").write_text(result.stdout, encoding="utf-8")
    (OUT / "build.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)

    archive = OUT / "libf316radar.a"
    sources = sorted(
        path for path in SOURCE.rglob("*")
        if path.is_file() and path.suffix in {".c", ".h", ".tsv", ".md"}
    )
    manifest = {
        "schema": "openmitrastar.f316-radar-classifier-offline/v1",
        "date": "2026-09-05",
        "status": "PASS",
        "classification": "PORTABLE_ARC700_CLASSIFIER_CALLBACK_DISABLED",
        "artifact": {
            "file": archive.name,
            "bytes": archive.stat().st_size,
            "sha256": sha256(archive),
            "reproducible_two_builds": True,
        },
        "lanes": {
            "preprocess": "PASS",
            "ssr_itlv": "PASS",
            "lsr_chirp": "PASS_WITH_CONSERVATIVE_BRANCHES",
            "postfilter": "PASS_CALLBACK_ELIGIBILITY_ONLY",
            "candidate_selector": "PASS_DATA_DRIVEN_ROUTE",
            "weather": "FAIL_CLOSED_PENDING_PHYSICAL_VECTORS",
            "unified_long_run": "PASS_100_BATCHES",
        },
        "authority": {
            "authoritative": False,
            "callback_allowed": False,
            "dfs_tx_authorized": False,
            "physical_vectors": False,
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
