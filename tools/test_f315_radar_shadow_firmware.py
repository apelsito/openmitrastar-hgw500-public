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
F314 = DEVICE / "f314-device-bound"
F315 = DEVICE / "f315-device-bound"
BASE = "openmitrastar-linux510-f315-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
DISTRO = "podman-mem9-tidb"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


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


def verify_sums() -> None:
    for line in (F315 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert sha256(F315 / name) == expected, name


def main() -> int:
    manifest = json.loads((F315 / "manifest.json").read_text(encoding="ascii"))
    source = json.loads((F314 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f315-radar-shadow-candidate/v1"
    assert manifest["source"]["base_candidate_sha256"] == source["artifacts"]["webformat"]["sha256"]
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["radar_shadow"]["callback_invocations"] == 0
    assert manifest["radar_shadow"]["dfs_tx_authorized"] is False
    assert manifest["radar_shadow"]["radar_start"] is False
    assert manifest["integration"]["radio_payload_file_count"] == 87
    assert manifest["storage"]["candidate_ends_before_store"] is True
    verify_sums()

    rootfs = F315 / f"{BASE}.rootfs.squashfs"
    with tempfile.TemporaryDirectory(prefix="f315-rootfs-") as directory:
        tree = Path(directory) / "root"
        proc = run_wsl(
            f"unsquashfs -no-progress -d {shlex.quote(wsl_path(tree))} "
            f"{shlex.quote(wsl_path(rootfs))} >/dev/null"
        )
        assert proc.returncode == 0, proc.stderr
        module_dir = tree / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g"
        provider = module_dir / "qtn_radar_shadow_f315.ko"
        qdrv = module_dir / "qdrv.ko"
        assert sha256(provider) == manifest["radar_shadow"]["provider"]["sha256"]
        assert sha256(qdrv) == manifest["radar_shadow"]["qdrv"]["sha256"]
        modinfo = run_wsl(f"modinfo {shlex.quote(wsl_path(qdrv))}")
        assert modinfo.returncode == 0, modinfo.stderr
        assert "qtn_radar_shadow_f315" in modinfo.stdout

        start = (tree / "usr/sbin/om-radio5-start").read_text(encoding="ascii")
        for marker in (
            "shadow_enable=1 shadow_arm=0",
            "radar-shadow-arm-missing",
            "callback_invocations=0",
            "configured=1",
        ):
            assert marker in start
        api = (tree / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="ascii")
        assert "radios/5g/dfs)" in api

        fake = Path(directory) / "proc"
        fake.mkdir()
        (fake / "status").write_text(
            "provider=native-linux-5.10\nbackend_ready=0\nfail_closed=1\n"
            "configured=1\npolling=1\nchannel=36\nbandwidth=80\n"
            "poll_runs=12\npoll_empty=4\npoll_unstable=0\nmmio_writes=931\n"
            "callback_invocations=0\nshadow_candidate_batches=2\n",
            encoding="ascii",
        )
        (fake / "snapshot").write_text(
            "sequence=12\nregisters_stable=1\nraw_count=4\nprocessed_count=3\n"
            "shadow_flags=0x01\nssr_matches=6\nitlv_matches=0\nlsr_matches=0\n"
            "chirp_rows=0\nweather_matches=0\n",
            encoding="ascii",
        )
        radarctl = tree / "usr/sbin/om-radarctl"
        result = run_wsl(
            f"OM_RADAR_PROC_ROOT={shlex.quote(wsl_path(fake))} sh "
            f"{shlex.quote(wsl_path(radarctl))} status"
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["available"] is True
        assert payload["backend_ready"] is False
        assert payload["authoritative"] is False
        assert payload["dfs_tx_authorized"] is False
        assert payload["callback_invocations"] == 0

    print("F315 firmware contract tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
