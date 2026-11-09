#!/usr/bin/env python3
"""Create an immutable offline plan for the F319 SPI ownership gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
F314_SHA256 = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
F319_SHA256 = "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9"
MODULE_SHA256 = "79436442b62110351fba44262a05ae0f2a9ffc87b36fabe74cc651112e431317"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    f314 = DEVICE / "f314-device-bound"
    f319 = DEVICE / "f319-device-bound"
    f314_manifest = json.loads((f314 / "manifest.json").read_text(encoding="ascii"))
    f319_manifest = json.loads((f319 / "manifest.json").read_text(encoding="ascii"))
    candidate = f319 / f319_manifest["artifacts"]["webformat"]["file"]
    module = ROOT / "outputs/kernel-port/f319-spi-owner-probe-20260905/qtn-topaz-spi-owner-probe.ko"

    checks = {
        "f314_exact_source": f314_manifest["artifacts"]["webformat"]["sha256"] == F314_SHA256,
        "f319_schema": f319_manifest["schema"] == "openmitrastar.f319-spi-owner-claim-candidate/v1",
        "candidate_hash": sha256(candidate) == F319_SHA256,
        "candidate_size": candidate.stat().st_size == 5292032,
        "full_slot_crc32": f319_manifest["artifacts"]["full_slot"]["crc32"] == "22d3802a",
        "full_slot_sha256": f319_manifest["artifacts"]["full_slot"]["sha256"] == "ad8bd328147e9fb03715b258bb99c69bbf0daa3b9c6a4dc993c0365ef7665601",
        "module_hash": sha256(module) == MODULE_SHA256,
        "module_autoload_disabled": f319_manifest["spi_owner_probe"]["autoload"] is False,
        "mmio_access_zero": f319_manifest["spi_owner_probe"]["mmio_reads"] == 0 and f319_manifest["spi_owner_probe"]["mmio_writes"] == 0,
        "mtd_registration_absent": f319_manifest["spi_owner_probe"]["mtd_registration"] is False,
        "persistent_writes_disabled": f319_manifest["storage"]["persistent_writes_enabled"] is False,
        "kernel_identical_to_f314": f319_manifest["artifacts"]["kernel_lzma"]["sha256"] == f314_manifest["artifacts"]["kernel_lzma"]["sha256"],
    }
    if not all(checks.values()):
        raise SystemExit(f"F319 preflight contract failed: {[key for key, value in checks.items() if not value]}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "outputs/preflight" / f"f319-spi-owner-claim-{stamp}"
    output = output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite evidence directory: {output}")
    output.mkdir(parents=True)

    plan = {
        "schema": "openmitrastar.f319-spi-owner-claim-plan/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_OFFLINE_PLAN",
        "target": {"model": "HGW-500BNA-QCv2 A2", "host": "192.168.1.90", "write_partition": "mtd4/linux_live"},
        "installed_source": {"version": "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device", "sha256": F314_SHA256},
        "candidate": {"path": str(candidate), "bytes": candidate.stat().st_size, "sha256": F319_SHA256, "full_slot_crc32": "22d3802a", "full_slot_sha256": "ad8bd328147e9fb03715b258bb99c69bbf0daa3b9c6a4dc993c0365ef7665601"},
        "module": {"path": "/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-spi-owner-probe.ko", "sha256": MODULE_SHA256, "autoload": False},
        "checks": checks,
        "required_ack": "OPENMITRASTAR_F319_SPI_OWNER_CLAIM_E33D8511",
        "physical_sequence": [
            "verify current F314 full-slot readback and protected-partition hashes",
            "start UART capture and preserve mtd3/linux_safety rollback",
            "write the exact candidate to mtd4 only and verify full-slot readback",
            "boot F319 and complete the unchanged F314 platform and dual-radio gate",
            "load qtn-topaz-spi-owner-probe.ko once",
            "verify resource_claimed=Y, controller_mapped=Y, read_count=0, write_count=0 and provider_ready=N",
            "verify /proc/mtd, all protected hashes, SSH, both radios and fatal count are unchanged",
            "unload the module and verify the resource is released",
            "keep F319 only on complete PASS; otherwise restore exact F314",
        ],
        "rollback": {"preferred": "exact F314 mtd4 image", "independent": "mtd3/linux_safety via UART ATGO"},
        "hardware_actions_performed": False,
        "execute_authorized": False,
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps({"status": plan["status"], "output": str(output), "candidate_sha256": F319_SHA256, "hardware_actions_performed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
