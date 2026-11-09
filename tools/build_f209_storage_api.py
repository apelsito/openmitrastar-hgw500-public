#!/usr/bin/env python3
"""Build F209 from F207 with read-only storage API and Advanced UI."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-2.9-f209"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f207-storage-readonly-probe-from-f205/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f207-storage-readonly-probe-from-f205-LZMA-OFFLINE-NO-FLASH"
F205_MANIFEST = ROOT / "work/mission-state/q3-persistent-composite-f205-runtime-signature-from-f203/build/manifest.json"
ASSETS = ROOT / "outputs/kernel-port/f209-storage-api-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f209-storage-api-from-f207/build"
BASE = "openmitrastar-linux510-q3-persistent-f209-storage-api-from-f207-LZMA-OFFLINE-NO-FLASH"
ROOTFS_WINDOW = 0x460000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000


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
        engine.PRODUCT_VERSION = "lyoko-foundation-2.9-f209"
        engine.ASSETS_SCHEMA = "openmitrastar.f209-storage-api-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f209-storage-api-rootfs-diff/v1"
        engine.REMOVE_PATHS = ()
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    old_rootfs_window = compose_engine.ROOTFS_WINDOW
    try:
        compose_engine.ROOTFS_WINDOW = ROOTFS_WINDOW
        with variant_context():
            rc = engine.main()
    finally:
        compose_engine.ROOTFS_WINDOW = old_rootfs_window
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    f205 = json.loads(F205_MANIFEST.read_text(encoding="ascii"))
    identity = frontend_identity()
    candidate = OUT / manifest["artifacts"]["webformat"]["file"]
    rootfs = OUT / manifest["artifacts"]["rootfs_squashfs"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F209 candidate overlaps or initializes lyoko_store")
    engine.run_wsl(
        "set -eu; "
        f"if unsquashfs -ll {engine.wsl_path(rootfs)!r} 2>/dev/null | "
        "grep -Eq 'device-dropbear-ed25519-host-key|device-identity/dropbear_ed25519_host_key'; "
        "then exit 1; fi"
    )
    manifest.update({
        "schema": "openmitrastar.f209-storage-api/v1",
        "classification": "F209_READONLY_STORAGE_API_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "release_eligible": False,
        "source": {"firmware": "F207", "installed_firmware": "F170"},
        "change_scope": {
            "storage_api": "rootfs/store geometry, mount state, SPI probe and write policy",
            "storage_ui": "Advanced read-only storage panel with raw diagnostic JSON",
            "writes": "no mount, format, erase or write path",
            "kernel_dtb_spi_packages_radios_security": "byte-identical to F207",
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
            "f207_webformat_sha256": source["artifacts"]["webformat"]["sha256"],
            "f207_kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
            "f207_rootfs_sha256": source["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "runtime_signature_verifier": f205["runtime_signature_verifier"],
        "storage": {
            **source["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "spi_probe": source["spi_probe"],
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, storage API geometry, JEDEC probe, zero writes, package verifier and dual-radio regression",
        },
        "known_limitations": [
            "storage layout and SPI verifier have not executed on physical hardware",
            "generic image uses ephemeral SSH identity until per-device personalization",
        ],
        "promotion_recommendation": "HOLD_FOR_RECOVERY_STORAGE_SPI_AND_NETWORK_HARDWARE_GATES",
        "private_key_scan": "PASS_PATH_ABSENT",
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO after recovery provisioning",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "hardware_actions_during_build": "none",
        },
    })
    manifest["layout"]["mtd_mapping"] = source["layout"]["mtd_mapping"]
    manifest["safety"].update({
        "lyoko_store": "read-only and unformatted",
        "module_registers_mtd": False,
        "module_has_write_path": False,
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
