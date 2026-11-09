#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F316 = DEVICE / "f316-device-bound"
F317 = DEVICE / "f317-device-bound"
BASE = "openmitrastar-linux510-f317-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
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
    manifest = json.loads((F317 / "manifest.json").read_text(encoding="ascii"))
    source = json.loads((F316 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f317-radiod-observer-candidate/v1"
    assert manifest["source"]["base_candidate_sha256"] == source["artifacts"]["webformat"]["sha256"]
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["integration"]["radio_modules_firmware_byte_identical_to_f316"] is True
    assert manifest["radiod_observer"]["mode"] == "observe"
    assert manifest["radiod_observer"]["automatic_apply"] is False
    assert manifest["radiod_observer"]["persistence"] == "volatile-/run"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    for line in (F317 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert sha256(F317 / name) == expected, name

    rootfs = F317 / f"{BASE}.rootfs.squashfs"
    with tempfile.TemporaryDirectory(prefix="f317-rootfs-") as directory:
        tree = Path(directory) / "root"
        result = run_wsl(
            f"unsquashfs -no-progress -d {shlex.quote(wsl_path(tree))} "
            f"{shlex.quote(wsl_path(rootfs))} >/dev/null"
        )
        assert result.returncode == 0, result.stderr
        radiod = tree / "usr/bin/lyoko-radiod"
        adapter = tree / "usr/bin/hgw500-radiod-adapter"
        assert sha256(radiod) == manifest["radiod_observer"]["engine"]["sha256"]
        assert sha256(adapter) == manifest["radiod_observer"]["adapter"]["sha256"]
        file_info = run_wsl(
            f"file {shlex.quote(wsl_path(radiod))} {shlex.quote(wsl_path(adapter))}"
        )
        assert file_info.returncode == 0
        assert file_info.stdout.count("statically linked") == 2
        assert file_info.stdout.count("ARC700") == 2

        scripts = (
            tree / "etc/init.d/S89-radiod",
            tree / "usr/sbin/om-radiod-snapshot",
            tree / "usr/sbin/om-radiod-status",
            tree / "usr/sbin/om-radiod-supervisor",
        )
        for script in scripts:
            syntax = run_wsl(f"sh -n {shlex.quote(wsl_path(script))}")
            assert syntax.returncode == 0, syntax.stderr
        combined = "\n".join(path.read_text(encoding="ascii") for path in scripts)
        assert "--observe-only" in combined
        assert "automatic_apply" in combined
        for forbidden in ("om-radioctl apply", "om-qtnctl apply", "/dev/mtd"):
            assert forbidden not in combined
        assert "optimization)" in (tree / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="ascii")
        assert (tree / "etc/openmitrastar/features/lyoko-radiod-v1").read_text(encoding="ascii").splitlines()[0] == "LYOKO_RADIOD_MODE=observe"
        packaged_schema = tree / "usr/share/lyoko/boards/schema.json"
        packaged_board = tree / "usr/share/lyoko/boards/hgw500bna-qcv2.json"
        assert sha256(packaged_schema) == sha256(ROOT / "work/platform/board-profile/schema.json")
        assert sha256(packaged_board) == sha256(ROOT / "work/platform/board-profile/hgw500bna-qcv2.json")
        board = json.loads(packaged_board.read_text(encoding="ascii"))
        assert board["writable_store"]["requires_layout_change"] is False
        assert board["writable_store"]["write_policy"] == "read-only"

    print("F317 firmware contract tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
