#!/usr/bin/env python3
"""Build F182 by adding the read-only SPI probe module to F180."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shutil

import build_f170_lyoko_foundation_runtime_fix as rootfs_engine
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
F180_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f180-storage-readonly-probe/build"
F180_BASE = "openmitrastar-linux510-q3-persistent-f180-storage-readonly-probe-LZMA-OFFLINE-NO-FLASH"
SPI_MODULE = ROOT / "outputs/kernel-port/f181-spi-readonly-probe-20260901/qtn-topaz-spi-probe.ko"
SOURCE_OVERLAY = ROOT / "versions/lyoko-spi-probe-1.0/overlay"
ASSETS = ROOT / "outputs/kernel-port/f182-spi-probe-boot-20260901"
OVERLAY = ASSETS / "combined-overlay"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f182-spi-probe-boot/build"
BASE = "openmitrastar-linux510-q3-persistent-f182-spi-probe-boot-LZMA-OFFLINE-NO-FLASH"
ROOTFS_WINDOW = 0x460000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_overlay() -> None:
    if not SPI_MODULE.is_file():
        raise SystemExit("missing F181 SPI probe module")
    if OVERLAY.exists():
        shutil.rmtree(OVERLAY)
    shutil.copytree(SOURCE_OVERLAY, OVERLAY)
    target = OVERLAY / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/diagnostics/qtn-topaz-spi-probe.ko"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SPI_MODULE, target)


@contextlib.contextmanager
def rootfs_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
    )
    old = {name: getattr(rootfs_engine, name) for name in names}
    try:
        rootfs_engine.SOURCE_BUILD = F180_BUILD
        rootfs_engine.SOURCE_BASE = F180_BASE
        rootfs_engine.FOUNDATION = OVERLAY
        rootfs_engine.OVERLAY = OVERLAY
        rootfs_engine.ASSETS = ASSETS
        rootfs_engine.OUT = OUT
        rootfs_engine.BASE = BASE
        rootfs_engine.PRODUCT_VERSION = "lyoko-foundation-1.3-f182"
        rootfs_engine.ASSETS_SCHEMA = "openmitrastar.f182-spi-probe-assets/v1"
        rootfs_engine.DIFF_SCHEMA = "openmitrastar.f182-spi-probe-rootfs-diff/v1"
        yield
    finally:
        for name, value in old.items():
            setattr(rootfs_engine, name, value)


@contextlib.contextmanager
def compose_context():
    names = ("ASSETS", "OUT", "BASE", "ROOTFS_WINDOW")
    old = {name: getattr(compose_engine, name) for name in names}
    try:
        compose_engine.ASSETS = ASSETS
        compose_engine.OUT = OUT
        compose_engine.BASE = BASE
        compose_engine.ROOTFS_WINDOW = ROOTFS_WINDOW
        yield
    finally:
        for name, value in old.items():
            setattr(compose_engine, name, value)


def main() -> int:
    prepare_overlay()
    with rootfs_context():
        rootfs_assets = rootfs_engine.prepare_assets()
    with compose_context():
        rc = compose_engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f180 = json.loads((F180_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f182-spi-probe-boot/v1",
        "classification": "F182_SPI_READONLY_BOOT_PROBE_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {"firmware": "F180", "installed_firmware": "F170"},
        "change_scope": {
            "module": "F181 read-only JEDEC/status probe",
            "boot": "nonfatal S31 load and /run state publication",
            "write_path": "absent",
            "kernel_dtb_radios_packages": "byte-identical to F180/F179",
        },
        "foundation_assets": rootfs_assets,
        "spi_probe": {
            "module_sha256": sha256(SPI_MODULE),
            "expected_jedec_id": "0xc22018",
            "expected_device": "MX25L12836E",
            "write_capable": False,
            "state_file": "/run/openmitrastar/spi-probe.state",
        },
        "parents": {
            "f180_webformat_sha256": f180["artifacts"]["webformat"]["sha256"],
            "f180_kernel_lzma_sha256": f180["artifacts"]["kernel_lzma"]["sha256"],
            "f180_rootfs_sha256": f180["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, module loaded, JEDEC 0xc22018, expected_device=Y and write_capable=N",
        },
        "safety": {
            "module_registers_mtd": False,
            "module_has_write_path": False,
            "lyoko_store": "read-only and unmounted",
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
        },
    })
    manifest["layout"]["rootfs_window_bytes"] = ROOTFS_WINDOW
    manifest["layout"]["rootfs_headroom_bytes"] = ROOTFS_WINDOW - manifest["artifacts"]["rootfs_squashfs"]["bytes"]
    manifest["layout"]["mtd_mapping"] = "read-only rootfs 0x90960000+0x00460000 and store 0x90dc0000+0x001c0000"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
