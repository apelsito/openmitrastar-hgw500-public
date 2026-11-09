from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import lyoko_ipk


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "versions/lyoko-foundation-2.8-f205/overlay/usr/bin/lyoko-pkg"
VERIFIER_NATIVE = ROOT / "outputs/packages/lyoko-ed25519-verify/lyoko-ed25519-verify-native"
VERIFIER_ARC = ROOT / "outputs/packages/lyoko-ed25519-verify/lyoko-ed25519-verify-arc"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def make_pkgbox(path: Path) -> None:
    path.write_bytes(b'#!/bin/sh\ncmd=$1\nshift\nexec "$cmd" "$@"\n')
    path.chmod(0o755)


def make_feed(root: Path) -> Path:
    recipe = root / "recipe"
    files = recipe / "files"
    files.mkdir(parents=True)
    (files / "lyoko-test").write_bytes(b"#!/bin/sh\nprintf 'runtime-signature-ok\\n'\n")
    (recipe / "package.json").write_text(json.dumps({
        "package": "lyoko-test",
        "version": "1.0.0-1",
        "architecture": lyoko_ipk.ARCH,
        "description": "Runtime signature test",
        "depends": [],
        "files": [{"source": "files/lyoko-test", "target": "/usr/bin/lyoko-test", "mode": "0755"}],
    }), encoding="ascii")
    packages = root / "packages"
    package = lyoko_ipk.build_package(recipe, packages)
    feed = root / "feed"
    key = Ed25519PrivateKey.generate()
    key_path = root / "feed-private.pem"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    lyoko_ipk.build_index(packages, feed, key_path)
    archives = feed / "archives"
    archives.mkdir()
    shutil.copy2(package, archives / package.name)
    make_pkgbox(root / "pkgbox")
    return feed


def run_manager(root: Path, feed: Path, run_root: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = (
        f"LYOKO_PKGBOX={shlex.quote(wsl_path(root / 'pkgbox'))} "
        f"LYOKO_FEED_ROOT={shlex.quote(wsl_path(feed))} "
        f"LYOKO_FEED_PUBLIC_KEY_RAW={shlex.quote(wsl_path(feed / 'lyoko-feed-ed25519.raw'))} "
        f"LYOKO_FEED_SIGNATURE_RAW={shlex.quote(wsl_path(feed / 'Packages.sig'))} "
        f"LYOKO_ED25519_VERIFY={shlex.quote(wsl_path(VERIFIER_NATIVE))} "
        f"LYOKO_PKG_RUN_ROOT={shlex.quote(run_root)} "
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


def test_valid_runtime_signature_allows_catalog_and_install() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f205-") as directory:
        root = Path(directory)
        feed = make_feed(root)
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        try:
            updated = run_manager(root, feed, run_root, "update")
            assert updated.returncode == 0, updated.stderr
            assert "signature_scope=build-and-runtime" in updated.stdout
            installed = run_manager(root, feed, run_root, "install", "lyoko-test")
            assert installed.returncode == 0, installed.stderr
            executed = run_manager(root, feed, run_root, "exec", "lyoko-test", "lyoko-test")
            assert executed.returncode == 0
            assert executed.stdout.strip() == "runtime-signature-ok"
        finally:
            cleanup(run_root)


def test_tampered_index_signature_and_key_are_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-f205-") as directory:
        root = Path(directory)
        feed = make_feed(root)
        run_root = f"/run/lyoko-packages/test-{uuid.uuid4().hex}"
        original_index = (feed / "Packages").read_bytes()
        original_signature = (feed / "Packages.sig").read_bytes()
        original_key = (feed / "lyoko-feed-ed25519.raw").read_bytes()
        try:
            (feed / "Packages").write_bytes(original_index + b"\n")
            tampered_index = run_manager(root, feed, run_root, "list")
            assert tampered_index.returncode != 0 and "feed-signature-invalid" in tampered_index.stderr
            (feed / "Packages").write_bytes(original_index)

            changed_signature = bytearray(original_signature); changed_signature[0] ^= 1
            (feed / "Packages.sig").write_bytes(changed_signature)
            tampered_signature = run_manager(root, feed, run_root, "verify", "lyoko-test")
            assert tampered_signature.returncode != 0 and "feed-signature-invalid" in tampered_signature.stderr
            (feed / "Packages.sig").write_bytes(original_signature)

            changed_key = bytearray(original_key); changed_key[0] ^= 1
            (feed / "lyoko-feed-ed25519.raw").write_bytes(changed_key)
            wrong_key = run_manager(root, feed, run_root, "plan", "lyoko-test")
            assert wrong_key.returncode != 0 and "feed-signature-invalid" in wrong_key.stderr
        finally:
            cleanup(run_root)


def test_verifier_artifacts_are_bounded_and_reproducible() -> None:
    manifest = json.loads((ROOT / "outputs/packages/lyoko-ed25519-verify/manifest.json").read_text(encoding="ascii"))
    assert manifest["native_valid_signature"] == "PASS"
    assert manifest["native_tampered_message"] == "REJECTED"
    assert manifest["native_tampered_signature"] == "REJECTED"
    assert manifest["arc_architecture"] == "ARC700 v4 ABI"
    assert manifest["arc_bytes"] <= 131072
    assert manifest["arc_atomic_instructions"] is False
    assert VERIFIER_NATIVE.is_file() and VERIFIER_ARC.is_file()
