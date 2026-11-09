from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F259 = PRIVATE / "f259-device-bound"
F260 = PRIVATE / "f260-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f260_source_uses_available_busybox_lock_cleanup() -> None:
    transaction = (
        ROOT / "versions/lyoko-foundation-4.9.3-f260/overlay/usr/sbin/om-config-transaction"
    ).read_text(encoding="utf-8")
    assert 'rm -rf "$lock_dir"' in transaction
    assert 'rmdir "$lock_dir"' not in transaction
    assert "kill -0 \"$lock_pid\"" in transaction


def test_f260_is_single_scope_and_preserves_f259_payload() -> None:
    manifest = json.loads((F260 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f260-config-lock-fix/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["transaction_hardening"]["stale_lock_recovery"].startswith("dead owner lock")
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/sbin/om-config-transaction",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F260 / named("f260", suffix)) == sha256(F259 / named("f259", suffix))
    assert manifest["package_runtime_fix"] == json.loads(
        (F259 / "manifest.json").read_text(encoding="ascii")
    )["package_runtime_fix"]


def test_f260_sha256sums_are_valid() -> None:
    entries = {}
    for line in (F260 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    excluded = {"SHA256SUMS", "known_hosts.f260"}
    files = {path.name for path in F260.iterdir() if path.is_file() and path.name not in excluded}
    assert set(entries) == files
    for name, digest in entries.items():
        assert sha256(F260 / name) == digest
