#!/usr/bin/env python3
"""Build F171 from F170 with honest health and no-op transaction semantics."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-1.0-f171"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f170-lyoko-foundation-runtime-fix-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f171-lyoko-foundation-health-fix-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build"
BASE = "openmitrastar-linux510-q3-persistent-f171-lyoko-foundation-health-fix-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def variant_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "OVERLAY", "ASSETS", "OUT", "BASE",
        "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
    )
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.SOURCE_BUILD = SOURCE_BUILD
        engine.SOURCE_BASE = SOURCE_BASE
        engine.OVERLAY = OVERLAY
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
        engine.PRODUCT_VERSION = "lyoko-foundation-1.0-f171"
        engine.ASSETS_SCHEMA = "openmitrastar.f171-lyoko-foundation-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f171-foundation-rootfs-diff/v1"
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
    manifest.update({
        "schema": "openmitrastar.f171-lyoko-foundation-health-fix/v1",
        "classification": "F171_LYOKO_FOUNDATION_HEALTH_FIX_FLASH_CANDIDATE",
        "source": {"firmware": "F170", "rootfs": str((SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").relative_to(ROOT))},
        "change_scope": {
            "api": "radio reads use native Linux 5.10 runtime interfaces",
            "health": "S90 retries IPv6 local policy after br0 exists and clears the stale degraded marker",
            "transactions": "verified no-op consumes pending state and advertises no rollback",
            "kernel_and_radios": "byte-identical to F167/F170",
        },
        "physical_validation": {"status": "NOT_RUN", "required": "ready boot state, API values, stable SSH identity and no-op transaction"},
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
