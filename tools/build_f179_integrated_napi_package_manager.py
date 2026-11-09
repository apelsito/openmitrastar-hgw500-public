#!/usr/bin/env python3
"""Build F179 from the F172 kernel and F177 product rootfs."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shlex
import shutil

import build_f170_lyoko_foundation_runtime_fix as rootfs_engine
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
F172_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f172-emac-napi128-from-f171/build"
F172_BASE = "openmitrastar-linux510-q3-persistent-f172-emac-napi128-from-f171-LZMA-OFFLINE-NO-FLASH"
F177_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f177-lyoko-package-manager-from-f176/build"
F177_BASE = "openmitrastar-linux510-q3-persistent-f177-lyoko-package-manager-from-f176-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f179-integrated-napi-package-manager-20260901"
EMPTY_OVERLAY = ASSETS / "release-overlay"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f179-integrated-napi-package-manager/build"
BASE = "openmitrastar-linux510-q3-persistent-f179-integrated-napi-package-manager-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def rootfs_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
    )
    old = {name: getattr(rootfs_engine, name) for name in names}
    try:
        rootfs_engine.SOURCE_BUILD = F177_BUILD
        rootfs_engine.SOURCE_BASE = F177_BASE
        rootfs_engine.FOUNDATION = EMPTY_OVERLAY
        rootfs_engine.OVERLAY = EMPTY_OVERLAY
        rootfs_engine.ASSETS = ASSETS
        rootfs_engine.OUT = OUT
        rootfs_engine.BASE = BASE
        rootfs_engine.PRODUCT_VERSION = "lyoko-foundation-1.3-f179"
        rootfs_engine.ASSETS_SCHEMA = "openmitrastar.f179-integrated-assets/v1"
        rootfs_engine.DIFF_SCHEMA = "openmitrastar.f179-integrated-rootfs-diff/v1"
        yield
    finally:
        for name, value in old.items():
            setattr(rootfs_engine, name, value)


@contextlib.contextmanager
def compose_context():
    names = ("ASSETS", "OUT", "BASE")
    old = {name: getattr(compose_engine, name) for name in names}
    try:
        compose_engine.ASSETS = ASSETS
        compose_engine.OUT = OUT
        compose_engine.BASE = BASE
        yield
    finally:
        for name, value in old.items():
            setattr(compose_engine, name, value)


def main() -> int:
    EMPTY_OVERLAY.mkdir(parents=True, exist_ok=True)
    with rootfs_context():
        rootfs_assets = rootfs_engine.prepare_assets()

    copies = {
        ".uncompressed.uImage": "kernel-squashfs.uncompressed.uImage",
        ".kernel.raw.bin": "kernel-squashfs.raw.bin",
        ".kernel.lzma": "kernel-squashfs.lzma",
        ".config": "kernel-squashfs.config",
        ".dtb": "topaz_mitrastar_squashfs.dtb",
        ".vmlinux": "kernel-squashfs.vmlinux",
    }
    for suffix, target in copies.items():
        shutil.copy2(F172_BUILD / f"{F172_BASE}{suffix}", ASSETS / target)

    with compose_context():
        rc = compose_engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f172 = json.loads((F172_BUILD / "manifest.json").read_text(encoding="ascii"))
    f177 = json.loads((F177_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f179-integrated-napi-package-manager/v1",
        "classification": "F179_INTEGRATED_NAPI128_PACKAGE_MANAGER_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {
            "kernel": "F172",
            "rootfs": "F177 plus release identity F179",
            "installed_firmware": "F170",
        },
        "change_scope": {
            "datapath": "F172 qtn-topaz-emac NAPI weight 128 plus read-only napi_weight telemetry",
            "product": "F177 Foundation 1.2, signed feed, pkgbox and volatile lyoko-pkg",
            "rootfs_delta_from_f177": "release identity only",
            "radios_tqe_bridge_rates": "unchanged",
        },
        "parents": {
            "f172_webformat_sha256": f172["artifacts"]["webformat"]["sha256"],
            "f172_kernel_lzma_sha256": f172["artifacts"]["kernel_lzma"]["sha256"],
            "f177_webformat_sha256": f177["artifacts"]["webformat"]["sha256"],
            "f177_rootfs_sha256": f177["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "foundation_assets": rootfs_assets,
        "package_manager": f177["package_manager"],
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "F171/F176 gates, lyoko-pkg ARC700 cycle and F172 three-run physical campaign",
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "storage_split": "not included; F178 remains an offline proposal",
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
