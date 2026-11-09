#!/usr/bin/env python3
"""Build F183 from F177 with the Foundation 1.4 capability registry."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-1.4-f183"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f177-lyoko-package-manager-from-f176/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f177-lyoko-package-manager-from-f176-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f183-capability-registry-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f183-capability-registry-from-f177/build"
BASE = "openmitrastar-linux510-q3-persistent-f183-capability-registry-from-f177-LZMA-OFFLINE-NO-FLASH"


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
        engine.PRODUCT_VERSION = "lyoko-foundation-1.4-f183"
        engine.ASSETS_SCHEMA = "openmitrastar.f183-capability-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f183-capability-rootfs-diff/v1"
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
    registry = json.loads((OVERLAY / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    manifest.update({
        "schema": "openmitrastar.f183-capability-registry/v1",
        "classification": "F183_LYOKO_CAPABILITY_REGISTRY_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {"firmware": "F177", "installed_firmware": "F170"},
        "change_scope": {
            "capabilities": "16 machine-readable feature states with evidence, risk and minimum UI mode",
            "frontend": "responsive capability matrix in Developer",
            "mutations": "none",
            "kernel_dtb_radios_packages": "byte-identical to F177",
        },
        "capability_registry": {
            "schema": registry["schema"],
            "items": len(registry["items"]),
            "states": sorted({item["state"] for item in registry["items"]}),
            "sha256": sha256(OVERLAY / "etc/lyoko/capabilities.json"),
        },
        "package_manager": source["package_manager"],
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "authenticated capabilities endpoint and responsive Developer matrix on hardware",
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
