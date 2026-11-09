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
F315 = DEVICE / "f315-device-bound"
F316 = DEVICE / "f316-device-bound"
BASE = "openmitrastar-linux510-f316-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
DISTRO = "podman-mem9-tidb"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def main() -> int:
    manifest = json.loads((F316 / "manifest.json").read_text(encoding="ascii"))
    source = json.loads((F315 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f316-radar-native-candidate/v1"
    assert manifest["source"]["base_candidate_sha256"] == source["artifacts"]["webformat"]["sha256"]
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["radar_native"]["authoritative_enable"] is True
    assert manifest["radar_native"]["weather_enable"] is True
    assert manifest["integration"]["radio_payload_file_count"] == 87
    assert manifest["storage"]["candidate_ends_before_store"] is True
    for line in (F316 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        assert sha256(F316 / name) == expected, name

    with tempfile.TemporaryDirectory(prefix="f316-rootfs-") as directory:
        tree = Path(directory) / "root"
        rootfs = F316 / f"{BASE}.rootfs.squashfs"
        extract = run_wsl(
            f"unsquashfs -no-progress -d {shlex.quote(wsl_path(tree))} "
            f"{shlex.quote(wsl_path(rootfs))} >/dev/null"
        )
        assert extract.returncode == 0, extract.stderr
        module_dir = tree / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g"
        assert not (module_dir / "qtn_radar_shadow_f315.ko").exists()
        provider = module_dir / "qtn_radar_native.ko"
        qdrv = module_dir / "qdrv.ko"
        assert sha256(provider) == manifest["radar_native"]["provider"]["sha256"]
        assert sha256(qdrv) == manifest["radar_native"]["qdrv"]["sha256"]
        modinfo = run_wsl(f"modinfo {shlex.quote(wsl_path(qdrv))}")
        assert modinfo.returncode == 0 and "qtn_radar_native" in modinfo.stdout
        feature = tree / "etc/openmitrastar/features/qtn-dfs-control-v1"
        assert feature.read_text(encoding="ascii") == "OPENMITRASTAR_QTN_DFS_CONTROL=1\n"
        start = (tree / "usr/sbin/om-radio5-start").read_text(encoding="ascii")
        for marker in (
            "qtn_radar_native.ko",
            "authoritative_enable=1 weather_enable=1",
            "backend_ready=1",
            "started=1",
            "callbacks_ready=1",
            "qtn_doth_value=1",
        ):
            assert marker in start
        for script in (tree / "usr/sbin/om-radio5-start", tree / "usr/sbin/om-radarctl"):
            syntax = run_wsl(f"sh -n {shlex.quote(wsl_path(script))}")
            assert syntax.returncode == 0, syntax.stderr

        fake = Path(directory) / "proc"
        fake.mkdir()
        (fake / "status").write_text(
            "provider=native-linux-5.10\nbackend_ready=1\nfail_closed=0\n"
            "started=1\ncallbacks_ready=1\nconfigured=1\npolling=0\n"
            "channel=36\nbandwidth=80\npoll_runs=0\npoll_empty=0\n"
            "poll_unstable=0\nmmio_writes=931\ncallback_invocations=0\n"
            "native_candidate_batches=0\nweather_enable=1\n"
            "authoritative_enable=1\n",
            encoding="ascii",
        )
        (fake / "snapshot").write_text(
            "sequence=0\nregisters_stable=1\nraw_count=0\nprocessed_count=0\n"
            "native_flags=0x00\nssr_matches=0\nitlv_matches=0\nlsr_matches=0\n"
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
        assert payload["schema"] == "lyoko.api.radar-native/v1"
        assert payload["available"] is True
        assert payload["backend_ready"] is True
        assert payload["authoritative"] is True
        assert payload["weather_enabled"] is True
        assert payload["callback_invocations"] == 0

    print("F316 firmware contract tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
