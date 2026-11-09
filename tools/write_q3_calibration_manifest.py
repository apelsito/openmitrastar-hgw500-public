#!/usr/bin/env python3
"""Regenerate the deterministic Q3 calibration/qdrv provenance manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RELEASE = "5.10.260-openmitrastar-radiohw"


def metadata(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    root = args.artifact.resolve()
    module_root = root / "rootfs/lib/modules" / RELEASE / "extra/quantenna"
    paths = {
        "qdrv.ko": module_root / "qdrv/qdrv.ko",
        "wlan.ko": module_root / "wlan/wlan.ko",
        "switch_vlan.ko": module_root / "platform/topaz/switch_vlan.ko",
        "module-manifest.tsv": root / "module-manifest.tsv",
    }
    for path in paths.values():
        if not path.is_file():
            raise SystemExit(f"missing artifact: {path}")
    manifest = {
        "schema": "openmitrastar.quantenna-linux510-calibration-oem-gpio4/v1",
        "date": "2026-08-21",
        "classification": "RAM-ONLY-NO-FLASH",
        "target": "mitrastar,hgw-500bna-qcv2",
        "changes": [
            "V8.1 calibration files are consumed from validated runtime tmpfs",
            "qdrv sequential pre-start allowlist accepts only gpio set wps 4 0",
            "zero-client GET_ASSOC_TBL uses the HGW/V89 lock-bounded fast path",
            "OEM GPIO4 WPS remains active-low polling and independent of the five-second product toggle",
        ],
        "artifacts": {name: metadata(path) for name, path in paths.items()},
        "flash_actions": False,
    }
    output = root / "BEACON_LIFETIME_MANIFEST.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    print(hashlib.sha256(output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
