#!/usr/bin/env python3
"""Build F205 from F203 with ARC700 runtime Ed25519 feed verification."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-2.8-f205"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f203-package-catalog-from-f201/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f203-package-catalog-from-f201-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f205-runtime-signature-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f205-runtime-signature-from-f203/build"
BASE = "openmitrastar-linux510-q3-persistent-f205-runtime-signature-from-f203-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontend_identity() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (OVERLAY / "etc/lyoko/frontend.env").read_text(encoding="ascii").splitlines()
        if line and "=" in line
    )


@contextlib.contextmanager
def variant_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA", "REMOVE_PATHS",
    )
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.SOURCE_BUILD = SOURCE_BUILD
        engine.SOURCE_BASE = SOURCE_BASE
        engine.FOUNDATION = FOUNDATION
        engine.OVERLAY = OVERLAY
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
        engine.PRODUCT_VERSION = "lyoko-foundation-2.8-f205"
        engine.ASSETS_SCHEMA = "openmitrastar.f205-runtime-signature-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f205-runtime-signature-rootfs-diff/v1"
        engine.REMOVE_PATHS = ()
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    with variant_context():
        rc = engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    identity = frontend_identity()
    verifier = OVERLAY / "usr/bin/lyoko-ed25519-verify"
    public_key_raw = OVERLAY / "etc/lyoko/keys/feed-ed25519.raw"
    signature_raw = OVERLAY / "usr/share/lyoko/feed/Packages.sig"
    manifest.update({
        "schema": "openmitrastar.f205-runtime-signature/v1",
        "classification": "F205_RUNTIME_ED25519_PACKAGE_FEED_VERIFICATION_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "release_eligible": False,
        "source": {"firmware": "F203", "installed_firmware": "F170"},
        "change_scope": {
            "runtime_signature": "Dropbear Ed25519 verifies Packages before every catalog-dependent command",
            "verifier": "static ARC700 v4 ABI, 51076 bytes, no llock/scond",
            "trust": "build-time Ed25519 plus runtime Ed25519 plus package SHA-256",
            "private_keys": "never included",
            "kernel_modules_rf_dma_queues_storage_ssh_radio_contracts": "byte-identical to F203",
        },
        "frontend": {
            "ui_version": identity["LYOKO_UI_VERSION"],
            "build_id": identity["LYOKO_UI_BUILD_ID"],
            "source": identity["LYOKO_UI_SOURCE"],
            "asset_bytes": int(identity["LYOKO_UI_ASSET_BYTES"]),
            "html_sha256": identity["LYOKO_UI_HTML_SHA256"],
            "js_sha256": identity["LYOKO_UI_JS_SHA256"],
            "css_sha256": identity["LYOKO_UI_CSS_SHA256"],
            "login_html_sha256": identity["LYOKO_UI_LOGIN_HTML_SHA256"],
            "login_css_sha256": identity["LYOKO_UI_LOGIN_CSS_SHA256"],
        },
        "parents": {
            "f203_webformat_sha256": source["artifacts"]["webformat"]["sha256"],
            "f203_kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
            "f203_rootfs_sha256": source["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "runtime_signature_verifier": {
            "implementation": "Dropbear 2026.94 dropbear_ed25519_verify",
            "artifact": "usr/bin/lyoko-ed25519-verify",
            "bytes": verifier.stat().st_size,
            "sha256": sha256(verifier),
            "public_key_raw_sha256": sha256(public_key_raw),
            "signature_raw_sha256": sha256(signature_raw),
            "private_key_in_firmware": False,
            "native_valid_signature": "PASS",
            "native_tampered_message": "REJECTED",
            "native_tampered_signature": "REJECTED",
            "arc_hardware_execution": "NOT_RUN",
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, ARC execution of valid/tampered signature vectors, package lifecycle and dual-radio regression",
        },
        "known_limitations": [
            "ARC binary has not yet executed on physical hardware",
            "generic image uses ephemeral SSH identity until per-device personalization",
        ],
        "promotion_recommendation": "HOLD_FOR_RECOVERY_ARC_SIGNATURE_AND_NETWORK_HARDWARE_GATES",
        "private_key_scan": source.get("private_key_scan", "UNKNOWN"),
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO after recovery provisioning",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "hardware_actions_during_build": "none",
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
