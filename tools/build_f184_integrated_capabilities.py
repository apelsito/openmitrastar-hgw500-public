#!/usr/bin/env python3
"""Build F184 from the F172 kernel and F183 capability-registry rootfs."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shutil

import build_f170_lyoko_foundation_runtime_fix as rootfs_engine
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
F172_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f172-emac-napi128-from-f171/build"
F172_BASE = "openmitrastar-linux510-q3-persistent-f172-emac-napi128-from-f171-LZMA-OFFLINE-NO-FLASH"
F183_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f183-capability-registry-from-f177/build"
F183_BASE = "openmitrastar-linux510-q3-persistent-f183-capability-registry-from-f177-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f184-integrated-capabilities-20260901"
EMPTY_OVERLAY = ASSETS / "release-overlay"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f184-integrated-capabilities/build"
BASE = "openmitrastar-linux510-q3-persistent-f184-integrated-capabilities-LZMA-OFFLINE-NO-FLASH"


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
        rootfs_engine.SOURCE_BUILD = F183_BUILD
        rootfs_engine.SOURCE_BASE = F183_BASE
        rootfs_engine.FOUNDATION = EMPTY_OVERLAY
        rootfs_engine.OVERLAY = EMPTY_OVERLAY
        rootfs_engine.ASSETS = ASSETS
        rootfs_engine.OUT = OUT
        rootfs_engine.BASE = BASE
        rootfs_engine.PRODUCT_VERSION = "lyoko-foundation-1.4-f184"
        rootfs_engine.ASSETS_SCHEMA = "openmitrastar.f184-integrated-assets/v1"
        rootfs_engine.DIFF_SCHEMA = "openmitrastar.f184-integrated-rootfs-diff/v1"
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
    f183 = json.loads((F183_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f184-integrated-capabilities/v1",
        "classification": "F184_INTEGRATED_NAPI128_CAPABILITY_UI_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {"kernel": "F172", "rootfs": "F183 plus release identity F184", "installed_firmware": "F170"},
        "change_scope": {
            "datapath": "F172 NAPI weight 128 plus read-only identity",
            "product": "F183 Foundation 1.4, package manager and capability registry",
            "rootfs_delta_from_f183": "release identity only",
            "storage_split": "not included",
        },
        "foundation_assets": rootfs_assets,
        "capability_registry": f183["capability_registry"],
        "package_manager": f183["package_manager"],
        "parents": {
            "f172_kernel_lzma_sha256": f172["artifacts"]["kernel_lzma"]["sha256"],
            "f172_webformat_sha256": f172["artifacts"]["webformat"]["sha256"],
            "f183_rootfs_sha256": f183["artifacts"]["rootfs_squashfs"]["sha256"],
            "f183_webformat_sha256": f183["artifacts"]["webformat"]["sha256"],
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "Foundation/package/capability gate plus F172 three-run Wi-Fi campaign",
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "storage_split": "not included",
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
