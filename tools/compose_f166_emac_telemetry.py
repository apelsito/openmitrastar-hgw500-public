#!/usr/bin/env python3
"""Compose F166 from F165 with read-only EMAC cause telemetry."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import compose_f164_squashfs_product as engine


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "outputs/kernel-port/f166-emac-cause-telemetry-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f166-emac-cause-telemetry/build"
BASE = "openmitrastar-linux510-q3-persistent-f166-emac-cause-telemetry-LZMA-OFFLINE-NO-FLASH"


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
    manifest["schema"] = "openmitrastar.f166-emac-cause-telemetry/v1"
    manifest["classification"] = "F166_EMAC_CAUSE_TELEMETRY_FLASH_CANDIDATE"
    manifest["change_scope"] = {
        "base": "F165 exact 0x620000 SquashFS MTD window",
        "kernel_emac": "read-only counters for IRQ causes, NAPI work, RX descriptor ownership and restart causes",
        "runtime_interface": "/sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats",
        "datapath_behavior": "unchanged: same IRQ mask, polling interval, poke threshold, restart threshold and cooldown",
        "rootfs_and_radios": "byte-identical product rootfs and radio payload from F165",
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

