from __future__ import annotations

import gzip
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import uuid

import lyoko_ipk


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "versions/lyoko-foundation-2.3-dev/overlay/usr/bin/lyoko-pkg"
PACKAGE = ROOT / "packages/lyoko/lyoko-sysinfo"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def make_pkgbox(path: Path) -> None:
    path.write_bytes(b'#!/bin/sh\ncmd=$1\nshift\nexec "$cmd" "$@"\n')
    path.chmod(0o755)


def run_manager(feed: Path, run_root: str, package: str = "lyoko-sysinfo") -> subprocess.CompletedProcess[str]:
    command = (
        f"LYOKO_PKGBOX='{wsl_path(feed.parent / 'pkgbox')}' "
        f"LYOKO_FEED_ROOT='{wsl_path(feed)}' LYOKO_PKG_RUN_ROOT='{run_root}' "
        f"sh '{wsl_path(MANAGER)}' install '{package}'"
    )
    return subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", command],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
    )


def make_feed(root: Path, package: Path) -> Path:
    feed = root / "feed"
    archive = feed / "archives" / package.name
    archive.parent.mkdir(parents=True)
    archive.write_bytes(package.read_bytes())
    members = lyoko_ipk.read_ar(package)
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["control.tar.gz"])), mode="r:") as control_archive:
        control_member = next(item for item in control_archive.getmembers() if item.name.lstrip("./") == "control")
        handle = control_archive.extractfile(control_member)
        assert handle is not None
        fields = lyoko_ipk.parse_control(handle.read())
    fields = dict(fields)
    fields.update(Filename=package.name, Size=str(package.stat().st_size), SHA256sum=lyoko_ipk.sha256_file(package))
    (feed / "Packages").write_bytes(lyoko_ipk.render_control(fields))
    make_pkgbox(root / "pkgbox")
    return feed


def malicious_symlink_package(root: Path) -> Path:
    valid = lyoko_ipk.build_package(PACKAGE, root / "valid")
    _, members = lyoko_ipk.read_control(valid)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        member = tarfile.TarInfo("./usr/bin/escape")
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/passwd"
        member.mode = 0o777
        archive.addfile(member)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as stream:
        stream.write(raw.getvalue())
    output = root / "malicious_1.0_arc700_uclibc_lyoko_v1.ipk"
    lyoko_ipk.write_ar(output, [("debian-binary", b"2.0\n"), ("control.tar.gz", members["control.tar.gz"]), ("data.tar.gz", compressed.getvalue())])
    return output


def test_runtime_installs_valid_package_atomically() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-runtime-") as directory:
        root = Path(directory)
        package = lyoko_ipk.build_package(PACKAGE, root / "built")
        feed = make_feed(root, package)
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            proc = run_manager(feed, run_root)
            assert proc.returncode == 0, proc.stderr
            assert "LYOKO_PKG_INSTALL_PASS" in proc.stdout
            probe = subprocess.run(
                ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "test", "-x", f"{run_root}/pkgs/lyoko-sysinfo/usr/bin/lyoko-sysinfo"],
                check=False,
            )
            assert probe.returncode == 0
        finally:
            subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "rm", "-rf", run_root], check=False)


def test_runtime_rejects_symlink_before_activation() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-runtime-") as directory:
        root = Path(directory)
        package = malicious_symlink_package(root)
        feed = make_feed(root, package)
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            proc = run_manager(feed, run_root, "lyoko-sysinfo")
            assert proc.returncode != 0
            assert "unsupported-package-entry" in proc.stderr
            probe = subprocess.run(
                ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "test", "!", "-e", f"{run_root}/pkgs/lyoko-sysinfo"],
                check=False,
            )
            assert probe.returncode == 0
        finally:
            subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "rm", "-rf", run_root], check=False)
