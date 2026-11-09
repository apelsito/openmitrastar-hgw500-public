from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import test_f205_runtime_signature as feed_test  # noqa: E402


MANAGER = ROOT / "versions/lyoko-foundation-4.0-f227/overlay/usr/bin/lyoko-pkg"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def run_manager(root: Path, feed: Path, run_root: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = (
        f"LYOKO_PKGBOX={shlex.quote(wsl_path(root / 'pkgbox'))} "
        f"LYOKO_FEED_ROOT={shlex.quote(wsl_path(feed))} "
        f"LYOKO_FEED_PUBLIC_KEY_RAW={shlex.quote(wsl_path(feed / 'lyoko-feed-ed25519.raw'))} "
        f"LYOKO_FEED_SIGNATURE_RAW={shlex.quote(wsl_path(feed / 'Packages.sig'))} "
        f"LYOKO_ED25519_VERIFY={shlex.quote(wsl_path(feed_test.VERIFIER_NATIVE))} "
        f"LYOKO_PKG_RUN_ROOT={shlex.quote(run_root)} LYOKO_PROC_MEMINFO=/proc/meminfo "
    )
    command = env + f"sh {shlex.quote(wsl_path(MANAGER))} " + " ".join(shlex.quote(arg) for arg in args)
    return subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", command],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def cleanup(run_root: str) -> None:
    subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "rm", "-rf", run_root], check=False)


def test_hardened_manager_installs_signed_package_and_cleans_lock() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f227-manager-") as directory:
        root = Path(directory)
        feed = feed_test.make_feed(root)
        feed_test.make_pkgbox(root / "pkgbox")
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            installed = run_manager(root, feed, run_root, "install", "lyoko-test")
            assert installed.returncode == 0, installed.stderr
            assert "LYOKO_PKG_INSTALL_PASS" in installed.stdout
            lock = subprocess.run(
                ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "test", "!", "-e", f"{run_root}/manager.lock"],
                check=False,
            )
            assert lock.returncode == 0
        finally:
            cleanup(run_root)


def test_hardened_manager_rejects_special_names_and_busy_lock() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f227-manager-") as directory:
        root = Path(directory)
        feed = feed_test.make_feed(root)
        feed_test.make_pkgbox(root / "pkgbox")
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            for name in (".", "..", "-option", "bad/name", "A"):
                rejected = run_manager(root, feed, run_root, "install", name)
                assert rejected.returncode != 0
                assert "invalid-package-name" in rejected.stderr
            subprocess.run(
                ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "mkdir", "-p", f"{run_root}/manager.lock"],
                check=True,
            )
            busy = run_manager(root, feed, run_root, "install", "lyoko-test")
            assert busy.returncode != 0
            assert "package-manager-busy" in busy.stderr
        finally:
            cleanup(run_root)
