from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F245 = PRIVATE / "f245-device-bound"
F248 = PRIVATE / "f248-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f248_source_opkg_contract_is_fail_closed() -> None:
    source = (ROOT / "versions/lyoko-foundation-5.0-f248/overlay/usr/bin/opkg").read_text(encoding="utf-8")
    manager = (ROOT / "versions/lyoko-foundation-5.0-f248/overlay/usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    for marker in ("opkg compatibility subset", "arc700_uclibc_lyoko_v1", "package-source-not-supported", 'exec "$manager"'):
        assert marker in source
    for forbidden in ("wget", "curl", "postinst", "preinst", "eval", "http://", "https://"):
        assert forbidden not in source
    assert "LYOKO_PKG_TEST_MODE" in manager
    assert "pkgbox=/usr/libexec/lyoko/pkgbox" in manager
    assert "feed_root=/usr/share/lyoko/feed" in manager


def test_f248_preserves_f245_kernel_and_is_offline_hold() -> None:
    manifest_path = F248 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f248-opkg-compat/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["opkg_compatibility"]["mode"] == "strict-subset"
    assert manifest["opkg_compatibility"]["network_fetch"] is False
    assert manifest["opkg_compatibility"]["local_archives"] is False
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert changed == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/bin/lyoko-pkg",
        "usr/bin/opkg",
        "usr/libexec/openmitrastar/om-api-v1",
        "usr/share/openmitrastar/web/dashboard.html",
        "www/app.js",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F248 / named("f248", suffix)) == sha256(F245 / named("f245", suffix))


def test_f248_builder_has_no_hardware_actions() -> None:
    source = (ROOT / "tools/build_f248_opkg_compat.py").read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
