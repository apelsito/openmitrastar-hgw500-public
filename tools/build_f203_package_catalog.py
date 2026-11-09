#!/usr/bin/env python3
"""Build F203 from F201 with bounded catalog and dependency management."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-2.7-f203"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f201-radio-contract-ui-from-f199/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f201-radio-contract-ui-from-f199-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f203-package-catalog-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f203-package-catalog-from-f201/build"
BASE = "openmitrastar-linux510-q3-persistent-f203-package-catalog-from-f201-LZMA-OFFLINE-NO-FLASH"


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
        engine.PRODUCT_VERSION = "lyoko-foundation-2.7-f203"
        engine.ASSETS_SCHEMA = "openmitrastar.f203-package-catalog-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f203-package-catalog-rootfs-diff/v1"
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
        "schema": "openmitrastar.f203-package-catalog/v1",
        "classification": "F203_BOUNDED_PACKAGE_CATALOG_DEPENDENCY_MANAGER_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "release_eligible": False,
        "source": {"firmware": "F201", "installed_firmware": "F170"},
        "change_scope": {
            "catalog": "immutable update, search, info, depends and plan commands",
            "dependencies": "exact-name resolver, maximum depth 16, cycle and missing dependency rejection",
            "removal": "reverse-dependency guard prevents breaking installed packages",
            "api": "catalog size and package-manager capabilities exposed read-only",
            "kernel_modules_rf_dma_queues_storage_ssh_radio_contracts": "byte-identical to F201",
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
            "f201_webformat_sha256": source["artifacts"]["webformat"]["sha256"],
            "f201_kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
            "f201_rootfs_sha256": source["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, catalog update/search/plan/install/remove on ARC700 and dual-radio regression",
        },
        "known_limitations": [
            "runtime repository signature verification remains build-time plus immutable SHA metadata",
            "generic image uses ephemeral SSH identity until per-device personalization",
        ],
        "promotion_recommendation": "HOLD_FOR_RECOVERY_PACKAGE_RUNTIME_AND_NETWORK_HARDWARE_GATES",
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
