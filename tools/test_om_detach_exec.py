from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/om_detach_exec.c"
PACKAGED = (
    ROOT
    / "versions/lyoko-foundation-6.8.2-f314-qtn-nondfs-guard"
    / "overlay/usr/sbin/om-detach-exec"
)
DISTRO = "podman-mem9-tidb"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    return f"/mnt/{drive}/{resolved.as_posix().split(':', 1)[1].lstrip('/')}"


def run_wsl(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "sh", "-c", command],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_source_closes_inherited_descriptors() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "close_inherited_fds(status_pipe[1])" in source
    assert "setsid()" in source
    assert "grandchild = fork()" in source
    assert "/run/openmitrastar/config/" in source


def test_packaged_binary_is_arc_static() -> None:
    assert PACKAGED.is_file()
    toolchain = "/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
    binary = wsl_path(PACKAGED)
    result = run_wsl(
        f"{toolchain}readelf -h {binary} | grep -Eq 'Machine:.*(ARC|ARCompact)' && "
        f"! {toolchain}readelf -l {binary} | grep -q 'Requesting program interpreter'"
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_launcher_returns_before_detached_child() -> None:
    with tempfile.TemporaryDirectory(prefix="om-detach-exec-") as directory:
        root = Path(directory)
        native = root / "om-detach-exec"
        child = root / "child.sh"
        child.write_bytes(b"#!/bin/sh\nsleep 2\nprintf 'detached-complete\\n'\n")
        child.chmod(0o755)
        build = run_wsl(f"cc -O2 {wsl_path(SOURCE)} -o {wsl_path(native)}")
        assert build.returncode == 0, build.stdout + build.stderr

        token = uuid.uuid4().hex
        log_dir = f"/tmp/openmitrastar-config-test/{token}"
        log = f"{log_dir}/watchdog.log"
        command = (
            f"mkdir -p {log_dir}; exec 9>/tmp/openmitrastar-config-test/{token}.held; "
            f"{wsl_path(native)} {log} /bin/sh {wsl_path(child)}"
        )
        started = time.monotonic()
        launched = run_wsl(command)
        elapsed = time.monotonic() - started
        assert launched.returncode == 0, launched.stdout + launched.stderr
        assert elapsed < 1.8, f"launcher retained inherited descriptors for {elapsed:.3f}s"

        time.sleep(2.3)
        observed = run_wsl(f"cat {log}; rm -rf {log_dir} /tmp/openmitrastar-config-test/{token}.held")
        assert observed.returncode == 0, observed.stdout + observed.stderr
        assert observed.stdout.strip() == "detached-complete"
