#!/usr/bin/env python3
"""Verify the private OEM/current/F185 handoff without extracting it."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME = "OpenMitraStar-HGW500-OEM-vs-F185-Full-Private-Handoff-20260901"
ZIP = ROOT / "handoff" / f"{NAME}.zip"
SIDECAR = ZIP.with_suffix(".zip.sha256")
PREFIX = f"{NAME}/"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    expected_zip = SIDECAR.read_text(encoding="ascii").split()[0]
    actual_zip = sha256_file(ZIP)
    if actual_zip != expected_zip:
        raise SystemExit("ZIP sidecar SHA-256 mismatch")
    with zipfile.ZipFile(ZIP) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"ZIP CRC failure: {bad}")
        names = set(archive.namelist())
        manifest = json.loads(archive.read(PREFIX + "bundle-manifest.json"))
        scan = json.loads(archive.read(PREFIX + "SECRET_SCAN.json"))
        if scan["result"] != "PASS":
            raise SystemExit("secret scan did not pass")
        if manifest["driver_counts"] != {"radio2g_modules": 10, "radio5g_modules": 25}:
            raise SystemExit("driver module count mismatch")
        required = {
            PREFIX + "HANDOFF_FOR_GPT.md",
            PREFIX + "comparison/OEM_VS_F185.md",
            PREFIX + "specs/HARDWARE_QUICK_REFERENCE.md",
            PREFIX + "dumps/README-CRITICAL.md",
            PREFIX + "dumps/oem-historical/hgw500_mtdblock0.bin",
            PREFIX + "dumps/oem-historical/hgw500_mtdblock6.bin",
            PREFIX + "dumps/physical-f159-capture/hgw500_mtdblock0.bin",
            PREFIX + "dumps/physical-f159-capture/hgw500_mtdblock5.bin",
            PREFIX + "dumps/installed-f170-reconstructed/hgw500_mtdblock0_uboot.bin",
            PREFIX + "dumps/installed-f170-reconstructed/hgw500_mtdblock6_rootfs_live_LOGICAL_OVERLAP.bin",
            PREFIX + "firmware/openmitrastar-f185/F185-mtd4-linux_live-full-slot-analysis-only.bin",
            PREFIX + "drivers/f185-rootfs/manifest.json",
            PREFIX + "docs/OPENMITRASTAR_PLATFORM_DOSSIER.md",
            PREFIX + "docs/OPENMITRASTAR_PRODUCT_SPEC.md",
        }
        missing = sorted(required - names)
        if missing:
            raise SystemExit("missing required entries: " + ", ".join(missing))
        forbidden = [name for name in names if re.search(r"(?i)(id_rsa|id_ed25519|known_hosts|ssh-root|accesos\.txt|txpower\.cal)", name)]
        if forbidden:
            raise SystemExit("forbidden secret-bearing filenames: " + ", ".join(forbidden))
        checksum_lines = archive.read(PREFIX + "MANIFEST.sha256").decode("utf-8").splitlines()
        for line in checksum_lines:
            expected, relative = line.split("  ", 1)
            digest = hashlib.sha256(archive.read(PREFIX + relative)).hexdigest()
            if digest != expected:
                raise SystemExit(f"internal checksum mismatch: {relative}")
    print(json.dumps({
        "status": "PASS",
        "zip": str(ZIP),
        "bytes": ZIP.stat().st_size,
        "sha256": actual_zip,
        "files": len(names),
        "driver_counts": manifest["driver_counts"],
        "installed_version": manifest["installed_version"],
        "candidate_version": manifest["candidate_version"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
