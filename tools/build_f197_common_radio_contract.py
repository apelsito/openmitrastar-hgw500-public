#!/usr/bin/env python3
"""Build F197 from F195 with a shared Realtek/Quantenna control contract."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-2.4-f197"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f195-package-hardening-from-f192/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f195-package-hardening-from-f192-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f197-common-radio-contract-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f197-common-radio-contract-from-f195/build"
BASE = "openmitrastar-linux510-q3-persistent-f197-common-radio-contract-from-f195-LZMA-OFFLINE-NO-FLASH"


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
        engine.PRODUCT_VERSION = "lyoko-foundation-2.4-f197"
        engine.ASSETS_SCHEMA = "openmitrastar.f197-common-radio-contract-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f197-common-radio-contract-rootfs-diff/v1"
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
    manifest.update({
        "schema": "openmitrastar.f197-common-radio-contract/v1",
        "classification": "F197_COMMON_RADIO_CONTROL_CONTRACT_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "release_eligible": False,
        "source": {"firmware": "F195", "installed_firmware": "F170"},
        "change_scope": {
            "radio_control": "new om-radioctl abstraction for Realtek and Quantenna",
            "api": "radio status, clients and transactions delegate to om-radioctl",
            "lifecycle": "firmware-ready, radio-ready, ap-ready and traffic-ready vocabulary",
            "scoped_restart": "fail-closed until physically certified",
            "kernel_modules_rf_dma_queues_storage_ssh_packages": "byte-identical to F195",
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
            "f195_webformat_sha256": source["artifacts"]["webformat"]["sha256"],
            "f195_kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
            "f195_rootfs_sha256": source["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, API parity, both radio control planes and bidirectional traffic",
        },
        "known_limitations": [
            "scoped restart is intentionally blocked until physical recovery tests pass",
            "generic image uses ephemeral SSH identity until per-device personalization",
        ],
        "promotion_recommendation": "HOLD_FOR_RECOVERY_SSH_RADIO_CONTRACT_AND_NETWORK_HARDWARE_GATES",
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
