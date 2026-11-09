from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import uuid

import pytest

import lyoko_ipk


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "versions/lyoko-foundation-2.7-f203/overlay/usr/bin/lyoko-pkg"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def make_pkgbox(path: Path) -> None:
    path.write_bytes(b'#!/bin/sh\ncmd=$1\nshift\nexec "$cmd" "$@"\n')
    path.chmod(0o755)


def make_recipe(root: Path, name: str, depends: list[str]) -> Path:
    package = root / name
    files = package / "files"
    files.mkdir(parents=True)
    command = files / name
    command.write_text(f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(name)}\n", encoding="ascii")
    command.chmod(0o755)
    (package / "package.json").write_text(json.dumps({
        "package": name,
        "version": "1.0.0-1",
        "architecture": lyoko_ipk.ARCH,
        "description": f"Test package {name}",
        "depends": depends,
        "kernel_abi": lyoko_ipk.KERNEL_ABI,
        "libc_abi": "uclibc",
        "platform": lyoko_ipk.PLATFORM,
        "files": [{"source": f"files/{name}", "target": f"/usr/bin/{name}", "mode": "0755"}],
    }, indent=2) + "\n", encoding="ascii")
    return package


def make_feed(root: Path, recipes: list[Path]) -> Path:
    built = root / "built"
    archives = root / "feed/archives"
    archives.mkdir(parents=True)
    rows: list[str] = []
    for recipe in recipes:
        package = lyoko_ipk.build_package(recipe, built)
        target = archives / package.name
        shutil.copy2(package, target)
        fields, _ = lyoko_ipk.read_control(package)
        fields = dict(fields)
        fields.update(Filename=package.name, Size=str(package.stat().st_size), SHA256sum=lyoko_ipk.sha256_file(package))
        rows.append(lyoko_ipk.render_control(fields).decode("utf-8").rstrip() + "\n")
    index = ("\n".join(rows)).encode("utf-8")
    feed = root / "feed"
    (feed / "Packages").write_bytes(index)
    (feed / "Packages.sig.json").write_text(json.dumps({
        "schema": "lyoko.package-feed-signature/v1",
        "algorithm": "ed25519",
        "key_id": "0123456789abcdef",
        "signed_file": "Packages",
        "sha256": hashlib.sha256(index).hexdigest(),
        "signature": "offline-test-placeholder",
    }, indent=2) + "\n", encoding="ascii")
    make_pkgbox(root / "pkgbox")
    return feed


def run_manager(root: Path, feed: Path, run_root: str, *args: str) -> subprocess.CompletedProcess[str]:
    command = (
        f"LYOKO_PKGBOX={shlex.quote(wsl_path(root / 'pkgbox'))} "
        f"LYOKO_FEED_ROOT={shlex.quote(wsl_path(feed))} "
        f"LYOKO_PKG_RUN_ROOT={shlex.quote(run_root)} "
        f"sh {shlex.quote(wsl_path(MANAGER))} " + " ".join(shlex.quote(arg) for arg in args)
    )
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
    subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "rm", "-rf", run_root],
        check=False,
    )


def test_catalog_and_dependency_lifecycle() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-pkg-f203-") as directory:
        root = Path(directory)
        core = make_recipe(root / "recipes", "lyoko-core", [])
        app = make_recipe(root / "recipes", "lyoko-app", ["lyoko-core"])
        feed = make_feed(root, [core, app])
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            updated = run_manager(root, feed, run_root, "update")
            assert updated.returncode == 0, updated.stderr
            assert "packages=2" in updated.stdout and "signature_scope=build-time" in updated.stdout
            assert "lyoko-app" in run_manager(root, feed, run_root, "search", "app").stdout
            assert "Depends: lyoko-core" in run_manager(root, feed, run_root, "info", "lyoko-app").stdout
            assert run_manager(root, feed, run_root, "depends", "lyoko-app").stdout.strip() == "lyoko-core"
            assert run_manager(root, feed, run_root, "plan", "lyoko-app").stdout.splitlines() == ["lyoko-core", "lyoko-app"]

            installed = run_manager(root, feed, run_root, "install", "lyoko-app")
            assert installed.returncode == 0, installed.stderr
            assert "package=lyoko-core" in installed.stdout and "package=lyoko-app" in installed.stdout
            listed = run_manager(root, feed, run_root, "list-installed").stdout
            assert "lyoko-core 1.0.0-1" in listed and "lyoko-app 1.0.0-1" in listed

            required = run_manager(root, feed, run_root, "remove", "lyoko-core")
            assert required.returncode != 0
            assert "LYOKO_PKG_REQUIRED_BY=lyoko-app" in required.stderr
            assert "package-required" in required.stderr
            assert run_manager(root, feed, run_root, "remove", "lyoko-app").returncode == 0
            assert run_manager(root, feed, run_root, "remove", "lyoko-core").returncode == 0
        finally:
            cleanup(run_root)


def test_missing_dependency_and_cycle_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-pkg-f203-") as directory:
        root = Path(directory)
        app = make_recipe(root / "missing", "lyoko-app", ["lyoko-core"])
        missing_feed = make_feed(root / "missing-feed", [app])
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            missing = run_manager(root / "missing-feed", missing_feed, run_root, "install", "lyoko-app")
            assert missing.returncode != 0
            assert "package-not-found" in missing.stderr
        finally:
            cleanup(run_root)

        cycle_root = root / "cycle"
        first = make_recipe(cycle_root / "recipes", "lyoko-first", ["lyoko-second"])
        second = make_recipe(cycle_root / "recipes", "lyoko-second", ["lyoko-first"])
        cycle_feed = make_feed(cycle_root, [first, second])
        cycle_run = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            cycle = run_manager(cycle_root, cycle_feed, cycle_run, "plan", "lyoko-first")
            assert cycle.returncode != 0
            assert "dependency-cycle" in cycle.stderr
        finally:
            cleanup(cycle_run)


@pytest.mark.parametrize("depends", [["bad (>= 1)"], ["lyoko-app"], ["lyoko-core", "lyoko-core"]])
def test_host_recipe_rejects_unsupported_dependency_forms(depends: list[str]) -> None:
    recipe = {
        "package": "lyoko-app",
        "version": "1.0.0-1",
        "architecture": lyoko_ipk.ARCH,
        "description": "test",
        "depends": depends,
    }
    with pytest.raises(ValueError):
        lyoko_ipk.control_fields(recipe)
