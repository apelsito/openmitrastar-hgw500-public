#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F314 = DEVICE / "f314-device-bound"
F319 = DEVICE / "f319-device-bound"
BASE = "openmitrastar-linux510-f319-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
DISTRO = "podman-mem9-tidb"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    path = path.resolve()
    return f"/mnt/{path.drive[0].lower()}/{path.as_posix()[3:]}"


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
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_f319_spi_owner_firmware.py"), "--replace-existing"],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads((F319 / "manifest.json").read_text(encoding="ascii"))
    source = json.loads((F314 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f319-spi-owner-claim-candidate/v1"
    assert manifest["source"]["base_candidate_sha256"] == source["artifacts"]["webformat"]["sha256"]
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["spi_owner_probe"]["autoload"] is False
    assert manifest["spi_owner_probe"]["mmio_reads"] == 0
    assert manifest["spi_owner_probe"]["mmio_writes"] == 0
    assert manifest["storage"]["persistent_writes_enabled"] is False
    for line in (F319 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert sha256(F319 / name) == expected, name

    rootfs = F319 / f"{BASE}.rootfs.squashfs"
    with tempfile.TemporaryDirectory(prefix="f319-rootfs-") as directory:
        tree = Path(directory) / "root"
        result = run_wsl(
            f"unsquashfs -no-progress -d {shlex.quote(wsl_path(tree))} {shlex.quote(wsl_path(rootfs))} >/dev/null"
        )
        assert result.returncode == 0, result.stderr
        module = tree / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-spi-owner-probe.ko"
        feature = tree / "etc/openmitrastar/features/spi-owner-probe-v1"
        assert sha256(module) == manifest["spi_owner_probe"]["module_sha256"]
        assert "AUTOLOAD=0" in feature.read_text(encoding="ascii")
        for script in (tree / "etc/init.d").glob("*"):
            if script.is_file():
                assert "qtn-topaz-spi-owner-probe" not in script.read_text(encoding="utf-8", errors="ignore")
    print("F319 SPI owner firmware tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
