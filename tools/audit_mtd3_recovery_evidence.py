#!/usr/bin/env python3
"""Classify existing mtd3 recovery evidence without touching hardware."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MTD3 = ROOT / "outputs/flash-backups/f159-physical-new-dump-20260831T2359/current-unit/hgw500_mtdblock3.bin"
F170_RESULT = ROOT / "work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build/flash-one-shot-20260901T111746Z/result.json"
BOOT_LOG = ROOT / "outputs/uart-live/boot-safety-after-recovery-20260817.log"
OUT = ROOT / "outputs/recovery/mtd3-current-evidence-20260901/result.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    flash = json.loads(F170_RESULT.read_text(encoding="utf-8"))
    text = BOOT_LOG.read_text(encoding="utf-8", errors="replace")
    digest = sha256(MTD3)
    checks = {
        "mtd3_dump_present": MTD3.is_file() and MTD3.stat().st_size == 0x7A0000,
        "mtd3_hash_matches_f170_attestation": digest == flash["protected_partitions"]["mtd3"],
        "bootselect_read_safety_slot": "spi_flash read 0x00040000 0x83000000 0x007a0000" in text,
        "uimage_crc_pass": "Verifying Checksum ... OK" in text,
        "oem_kernel_started": "Linux version 2.6.35.12" in text,
        "rootfs_mount_failed": "VFS: Unable to mount root fs" in text,
        "management_proven": False,
        "ssh_proven": False,
        "flash_written_by_audit": False,
        "bootenv_written_by_audit": False,
    }
    result = {
        "schema": "openmitrastar.mtd3-recovery-evidence/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE",
        "recovery_ready": False,
        "mtd3": {"bytes": MTD3.stat().st_size, "sha256": digest},
        "evidence": str(BOOT_LOG.relative_to(ROOT)),
        "checks": checks,
        "conclusion": "mtd3 has a valid bootable kernel payload but is not an independently bootable recovery system",
        "next_required_artifact": "a safety-slot image whose embedded DTB maps rootfs into the physical mtd3 window",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
