#!/usr/bin/env python3
"""Build the temporary ARC700 endpoint used by the F301 VLAN 4090 gate."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/f301_vlan_endpoint.c"
OUTPUT_DIR = ROOT / "outputs/kernel-port/f301-vlan-gate"
ARC_OUTPUT = OUTPUT_DIR / "f301-vlan-endpoint.arc700"
MANIFEST = OUTPUT_DIR / "manifest.json"
DISTRO = "podman-mem9-tidb"
TOOLCHAIN = ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
SYSROOT = "/home/user/openmitrastar-uclibc-noatomic-sysroot"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    return f"/mnt/{drive}/{resolved.as_posix().split(':', 1)[1].lstrip('/')}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_wsl(script: str) -> str:
    proc = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout or f"WSL failed rc={proc.returncode}")
    return proc.stdout


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source = shlex.quote(wsl_path(SOURCE))
    arc_output = shlex.quote(wsl_path(ARC_OUTPUT))
    arc_output_2 = shlex.quote(wsl_path(OUTPUT_DIR / ".f301-vlan-endpoint.arc700.second"))
    compiler = shlex.quote(wsl_path(Path(str(TOOLCHAIN) + "gcc")))
    readelf = shlex.quote(wsl_path(Path(str(TOOLCHAIN) + "readelf")))
    script = f"""
set -eu
common='-std=c99 -Os -static -s -Wall -Wextra -Werror'
{compiler} --sysroot={shlex.quote(str(SYSROOT))} -mno-atomic -fno-stack-protector $common -o {arc_output} {source}
{compiler} --sysroot={shlex.quote(str(SYSROOT))} -mno-atomic -fno-stack-protector $common -o {arc_output_2} {source}
cmp {arc_output} {arc_output_2}
rm -f {arc_output_2}
{readelf} -h {arc_output} | grep -q 'ARC700, v4 ABI'
"""
    output = run_wsl(script)
    manifest = {
        "schema": "openmitrastar.f301-vlan-endpoint-build/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "temporary RAM-only VLAN 4090 control and UDP echo endpoint",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": sha256(SOURCE),
        "artifact": {
            "file": ARC_OUTPUT.name,
            "bytes": ARC_OUTPUT.stat().st_size,
            "sha256": sha256(ARC_OUTPUT),
            "architecture": "ARC700 v4 ABI",
            "static": True,
            "reproducible_two_builds": True,
        },
        "contract": {
            "vlan_id": 4090,
            "runtime_root": "/run/openmitrastar/vlan4090",
            "persistent_writes": False,
            "mtd_writes": False,
            "bridge_mutation": False,
            "qdrv_vlan_path": False,
        },
        "compile_output": output.strip(),
        "hardware_actions": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
