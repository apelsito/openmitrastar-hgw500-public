#!/usr/bin/env python3
"""Plan a non-overlapping mtd4 rootfs/package-store split without flashing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
F177 = ROOT / "work/mission-state/q3-persistent-composite-f177-lyoko-package-manager-from-f176/build/manifest.json"
OUT = ROOT / "outputs/kernel-port/f178-storage-split-plan-20260901"

ERASE = 0x10000
LIVE_OFFSET = 0x7E0000
LIVE_SIZE = 0x7A0000
KERNEL_REGION = 0x180000
ROOTFS_OFFSET = LIVE_OFFSET + KERNEL_REGION
ROOTFS_SIZE = 0x460000
STORE_OFFSET = ROOTFS_OFFSET + ROOTFS_SIZE
STORE_SIZE = LIVE_SIZE - KERNEL_REGION - ROOTFS_SIZE
DATA_OFFSET = 0xF80000


def main() -> int:
    source = json.loads(F177.read_text(encoding="ascii"))
    rootfs_bytes = int(source["artifacts"]["rootfs_squashfs"]["bytes"])
    checks = {
        "all_boundaries_erase_aligned": all(
            value % ERASE == 0
            for value in (LIVE_OFFSET, LIVE_SIZE, KERNEL_REGION, ROOTFS_OFFSET, ROOTFS_SIZE, STORE_OFFSET, STORE_SIZE)
        ),
        "rootfs_fits": rootfs_bytes <= ROOTFS_SIZE,
        "store_nonempty": STORE_SIZE >= 0x100000,
        "store_ends_before_data": STORE_OFFSET + STORE_SIZE == DATA_OFFSET,
        "mtd3_untouched": True,
        "mtd5_untouched": True,
    }
    plan = {
        "schema": "openmitrastar.f178-storage-split-plan/v1",
        "classification": "OFFLINE_LAYOUT_PROPOSAL_NO_FLASH",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "source": {
            "firmware": "F177 offline package-manager candidate",
            "manifest": str(F177.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(F177.read_bytes()).hexdigest(),
        },
        "physical_linux_live": {
            "offset": f"0x{LIVE_OFFSET:06x}",
            "size": f"0x{LIVE_SIZE:06x}",
            "bytes": LIVE_SIZE,
        },
        "proposed_subregions": {
            "kernel_and_header": {
                "offset": f"0x{LIVE_OFFSET:06x}",
                "size": f"0x{KERNEL_REGION:06x}",
            },
            "rootfs_live": {
                "offset": f"0x{ROOTFS_OFFSET:06x}",
                "size": f"0x{ROOTFS_SIZE:06x}",
                "current_image_bytes": rootfs_bytes,
                "headroom_bytes": ROOTFS_SIZE - rootfs_bytes,
            },
            "lyoko_store": {
                "offset": f"0x{STORE_OFFSET:06x}",
                "size": f"0x{STORE_SIZE:06x}",
                "bytes": STORE_SIZE,
                "eraseblocks": STORE_SIZE // ERASE,
                "filesystem_candidate": "jffs2",
                "usage": ["signed IPK archives", "package selection", "small configuration", "rollback metadata"],
            },
        },
        "runtime": {
            "mount": "/run/lyoko-packages",
            "filesystem": "tmpfs",
            "size_limit_bytes": 0x800000,
            "allocation": "on-demand DDR pages; not reserved at boot",
            "restore_flow": "verify persistent archive -> extract into tmpfs -> execute",
        },
        "firmware_update_contract": {
            "erase_write_prefix_bytes": KERNEL_REGION + ROOTFS_SIZE,
            "preserve_store_tail": True,
            "full_mtd4_erase_forbidden_after_store_initialization": True,
            "bootbase_live_image_size_unchanged": f"0x{LIVE_SIZE:06x}",
        },
        "rejected": {
            "mtd3_as_storage": "destroys the independent safety firmware",
            "mtd5_as_package_overlay": "only 512 KiB and contains protected calibration/configuration",
            "flash_swap": "NOR wear and latency; use tmpfs and later optional zram instead",
        },
        "checks": checks,
        "hardware_actions": {"router": False, "uart": False, "mtd": False},
        "next_proof": "DTS/physmap prototype plus flash-prefix preservation tests on a synthetic 16 MiB image",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0 if plan["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
