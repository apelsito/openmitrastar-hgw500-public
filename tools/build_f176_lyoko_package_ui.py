#!/usr/bin/env python3
"""Build F176 from F174 with the signed-package API and UI."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-1.2-f176"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f174-lyoko-package-base-from-f173/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f174-lyoko-package-base-from-f173-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f176-lyoko-package-ui-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f176-lyoko-package-ui-from-f174/build"
BASE = "openmitrastar-linux510-q3-persistent-f176-lyoko-package-ui-from-f174-LZMA-OFFLINE-NO-FLASH"


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
        engine.PRODUCT_VERSION = "lyoko-foundation-1.2-f176"
        engine.ASSETS_SCHEMA = "openmitrastar.f176-lyoko-package-ui-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f176-lyoko-package-ui-rootfs-diff/v1"
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
    source = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f176-lyoko-package-ui/v1",
        "classification": "F176_LYOKO_SIGNED_PACKAGE_UI_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {
            "firmware": "F174 offline package-base candidate; F170 currently installed",
            "rootfs": str((SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").relative_to(ROOT)),
        },
        "change_scope": {
            "api": "read-only /api/v1/packages inventory",
            "frontend": "Developer package panel and mobile overflow fix",
            "package_payload": "byte-identical to F174",
            "kernel_dtb_radios": "byte-identical to F174/F173/F171/F170/F167",
            "runtime_install": "disabled",
        },
        "package_state": source["package_state"],
        "source_kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "F174 base checks plus authenticated packages endpoint and responsive Developer view",
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
