#!/usr/bin/env python3
"""Compose F165 from the exact-window SquashFS kernel assets."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import compose_f164_squashfs_product as engine


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "outputs/kernel-port/f165-squashfs-exact-mtd-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f165-squashfs-exact-mtd/build"
BASE = "openmitrastar-linux510-q3-persistent-f165-squashfs-exact-mtd-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def variant_context():
    names = ("ASSETS", "OUT", "BASE")
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
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
    manifest["schema"] = "openmitrastar.f165-squashfs-exact-mtd/v1"
    manifest["classification"] = "F165_SQUASHFS_EXACT_MTD_FLASH_CANDIDATE"
    manifest["change_scope"] = {
        "base": "F164 first persistent SquashFS boot",
        "physmap": "use exact resource size when no GPIO bank expansion is present",
        "rootfs_live": "expose the complete 0x620000 read-only window",
        "rootfs_and_radios": "byte-identical product rootfs and radio payload from F164",
    }
    manifest["candidate_eligible"] = True
    manifest["flash_supported"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
