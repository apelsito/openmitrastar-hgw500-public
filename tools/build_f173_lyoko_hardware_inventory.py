#!/usr/bin/env python3
"""Build F173 from F171 with the Lyoko Foundation 1.1 hardware inventory."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-1.1-f173"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f171-lyoko-foundation-health-fix-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f173-lyoko-hardware-inventory-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f173-lyoko-hardware-inventory-from-f171/build"
BASE = "openmitrastar-linux510-q3-persistent-f173-lyoko-hardware-inventory-from-f171-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def variant_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
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
        engine.PRODUCT_VERSION = "lyoko-foundation-1.1-f173"
        engine.ASSETS_SCHEMA = "openmitrastar.f173-lyoko-hardware-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f173-lyoko-hardware-rootfs-diff/v1"
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
    source_manifest = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f173-lyoko-hardware-inventory/v1",
        "classification": "F173_LYOKO_HARDWARE_INVENTORY_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {
            "firmware": "F171 offline candidate; F170 currently installed",
            "rootfs": str((SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").relative_to(ROOT)),
        },
        "change_scope": {
            "hardware_api": "three buttons, six LEDs, honest thermal availability and watchdog registration",
            "frontend": "structured hardware summary for Normal/Advanced UI",
            "kernel_dtb_radios": "byte-identical to F171/F170/F167",
            "configuration": "no new writable hardware controls",
        },
        "source_kernel_lzma_sha256": source_manifest["artifacts"]["kernel_lzma"]["sha256"],
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "F171 base gate plus hardware endpoint comparison with live sysfs/procfs",
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
