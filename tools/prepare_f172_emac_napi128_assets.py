#!/usr/bin/env python3
"""Build F172 kernel assets and retain the F171 rootfs byte-for-byte."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import prepare_f164_squashfs_assets as engine


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/kernel-port/f172-emac-napi128-20260901"
KERNEL_OUT = "/home/user/openmitrastar-build/f172-emac-napi128"
F171_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build"
F171_BASE = "openmitrastar-linux510-q3-persistent-f171-lyoko-foundation-health-fix-LZMA-OFFLINE-NO-FLASH"


def main() -> int:
    old_out = engine.OUT
    old_kernel_out = engine.KERNEL_OUT
    try:
        engine.OUT = OUT
        engine.KERNEL_OUT = KERNEL_OUT
        rc = engine.main()
    finally:
        engine.OUT = old_out
        engine.KERNEL_OUT = old_kernel_out
    if rc:
        return rc

    source_rootfs = F171_BUILD / f"{F171_BASE}.rootfs.squashfs"
    target_rootfs = OUT / "rootfs-product-xz-128k.squashfs"
    if not source_rootfs.is_file():
        raise SystemExit(f"missing F171 rootfs: {source_rootfs}")
    shutil.copy2(source_rootfs, target_rootfs)

    manifest_path = OUT / "assets-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f172-emac-napi128-assets/v1",
        "source_rootfs": {
            "path": str(source_rootfs.relative_to(ROOT)),
            "bytes": source_rootfs.stat().st_size,
            "sha256": engine.sha256(source_rootfs),
            "policy": "byte-identical F171 Lyoko health/transactions rootfs",
        },
        "single_variable": {
            "path": "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c",
            "old": "netif_napi_add(..., 64)",
            "new": "QTN_TOPAZ_EMAC_NAPI_WEIGHT=128",
        },
        "hardware_actions": {
            "router": False,
            "uart": False,
            "reboot": False,
            "mtd": False,
            "windows_wifi": False,
        },
    })
    manifest["artifacts"][target_rootfs.name] = {
        "bytes": target_rootfs.stat().st_size,
        "sha256": engine.sha256(target_rootfs),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
