from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F260 = PRIVATE / "f260-device-bound"
F261 = PRIVATE / "f261-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f261_source_uses_real_busybox_ifconfig_path() -> None:
    qtnctl = (
        ROOT / "versions/lyoko-foundation-4.9.4-f261/overlay/usr/sbin/om-qtnctl"
    ).read_text(encoding="utf-8")
    assert "ifconfig=${OM_IFCONFIG:-/bin/ifconfig}" in qtnctl
    assert "ifconfig=${OM_IFCONFIG:-/sbin/ifconfig}" not in qtnctl


def test_f261_is_single_scope_and_preserves_f260_payload() -> None:
    manifest = json.loads((F261 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f261-qtn-ifconfig-path-fix/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_qtn_control"]["ifconfig_path"] == "/bin/ifconfig"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/sbin/om-qtnctl",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F261 / named("f261", suffix)) == sha256(F260 / named("f260", suffix))


def test_f261_sha256sums_are_valid() -> None:
    entries = {}
    for line in (F261 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    excluded = {"SHA256SUMS", "known_hosts.f261"}
    files = {path.name for path in F261.iterdir() if path.is_file() and path.name not in excluded}
    assert set(entries) == files
    for name, digest in entries.items():
        assert sha256(F261 / name) == digest
