from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F258 = PRIVATE / "f258-device-bound"
F259 = PRIVATE / "f259-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f259_source_uses_gunzip_multicall_basename() -> None:
    overlay = ROOT / "versions/lyoko-foundation-4.9.2-f259/overlay"
    manager = (overlay / "usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    dispatcher = (overlay / "usr/libexec/lyoko/pkgbox-run").read_text(encoding="utf-8")
    ar_binary = overlay / "usr/libexec/lyoko/ar"
    gunzip_binary = overlay / "usr/libexec/lyoko/gunzip"

    assert '"$pkgbox" gunzip -c "$tmp/data.tar.gz"' in manager
    assert '"$pkgbox" gzip -dc "$tmp/data.tar.gz"' not in manager
    assert 'gunzip) exec /usr/libexec/lyoko/gunzip "$@"' in dispatcher
    assert sha256(gunzip_binary) == sha256(ar_binary)


def test_f259_is_a_single_scope_test_candidate() -> None:
    manifest = json.loads((F259 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f259-package-decompress-fix/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["contracts"]["bootbase"] == "PASS"
    assert manifest["package_runtime_fix"]["gunzip_basename_binary"] == "/usr/libexec/lyoko/gunzip"
    assert manifest["package_runtime_fix"]["single_scope"] == "package decompression only"
    assert manifest["storage"]["store_erased_ff"] is True
    assert manifest["storage"]["candidate_ends_before_store"] is True

    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert changed == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/bin/lyoko-pkg",
        "usr/libexec/lyoko/gunzip",
        "usr/libexec/lyoko/pkgbox-run",
    }


def test_f259_preserves_f258_kernel_config_and_dtb() -> None:
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F259 / named("f259", suffix)) == sha256(F258 / named("f258", suffix))


def test_f259_sha256sums_are_complete_and_valid() -> None:
    entries = {}
    for line in (F259 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    excluded = {"SHA256SUMS", "known_hosts.f259"}
    files = {path.name for path in F259.iterdir() if path.is_file() and path.name not in excluded}
    assert set(entries) == files
    for name, digest in entries.items():
        assert sha256(F259 / name) == digest
