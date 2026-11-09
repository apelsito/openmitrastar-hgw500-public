#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "versions/lyoko-foundation-7.1.0-f317-radiod-observer/overlay"
RADIOD_MANIFEST = ROOT / "outputs/userland/lyoko-radiod-arc700-20260905/manifest.json"
ADAPTER_MANIFEST = ROOT / "outputs/userland/hgw500-radiod-adapter-arc700-20260905/manifest.json"
DISTRO = "podman-mem9-tidb"


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
        timeout=60,
        check=False,
    )


def main() -> int:
    snapshot = OVERLAY / "usr/sbin/om-radiod-snapshot"
    supervisor = OVERLAY / "usr/sbin/om-radiod-supervisor"
    status = OVERLAY / "usr/sbin/om-radiod-status"
    init = OVERLAY / "etc/init.d/S89-radiod"
    api = OVERLAY / "usr/libexec/openmitrastar/om-api-v1"
    feature = OVERLAY / "etc/openmitrastar/features/lyoko-radiod-v1"
    profile = OVERLAY / "etc/lyoko/radiod/hgw500bna-qcv2.profile"

    for script in (snapshot, supervisor, status, init):
        result = run_wsl(f"sh -n {shlex.quote(wsl_path(script))}")
        assert result.returncode == 0, result.stderr

    supervisor_text = supervisor.read_text(encoding="ascii")
    assert "--observe-only" in supervisor_text
    assert "last-decision" in supervisor_text
    assert "decisions.log" not in supervisor_text
    for forbidden in ("om-radioctl apply", "om-qtnctl apply", "/dev/mtd"):
        assert forbidden not in supervisor_text
    assert "state=ENABLED" in init.read_text(encoding="ascii")
    assert "optimization)" in api.read_text(encoding="ascii")
    assert feature.read_text(encoding="ascii").splitlines() == [
        "LYOKO_RADIOD_MODE=observe",
        "LYOKO_RADIOD_INTERVAL_SECONDS=60",
        "LYOKO_RADIOD_SAMPLE_SECONDS=5",
        "LYOKO_RADIOD_PERSISTENCE=volatile",
    ]
    assert "board_id=mitrastar-hgw-500bna-qcv2" in profile.read_text(encoding="ascii")

    radiod = json.loads(RADIOD_MANIFEST.read_text(encoding="ascii"))
    adapter = json.loads(ADAPTER_MANIFEST.read_text(encoding="ascii"))
    assert radiod["status"] == "PASS" and radiod["binary"]["static"] is True
    assert adapter["status"] == "PASS" and adapter["binary"]["static"] is True

    with tempfile.TemporaryDirectory(prefix="f317-status-") as directory:
        run = Path(directory)
        (run / "status.env").write_text("mode=observe\npersistence=volatile\n", encoding="ascii")
        empty = run_wsl(
            f"OM_RADIOD_RUN={shlex.quote(wsl_path(run))} sh {shlex.quote(wsl_path(status))}"
        )
        assert empty.returncode == 0, empty.stderr
        empty_json = json.loads(empty.stdout)
        assert empty_json["last_decision"] == ""
        assert empty_json["automatic_apply"] is False

        (run / "last-sequence").write_text("7\n", encoding="ascii")
        (run / "last-decision").write_text(
            "DECISION propose 2 2g:1/20/20/0:1:1800 5g:44/80/21/0:2:1800\n",
            encoding="ascii",
        )
        populated = run_wsl(
            f"OM_RADIOD_RUN={shlex.quote(wsl_path(run))} sh {shlex.quote(wsl_path(status))}"
        )
        assert populated.returncode == 0, populated.stderr
        payload = json.loads(populated.stdout)
        assert payload["last_sequence"] == 7
        assert payload["last_decision"].startswith("DECISION propose")
        assert payload["sensitive_identifiers"] is False

    print("F317 radiod observer tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
