#!/usr/bin/env python3
"""Promote the exact F246 bytes into an authorized-test F247 envelope.

This is a filesystem-only operation. It never opens UART, network sockets or
router flash. F247 remains hardware-unproven until its guarded campaign passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from init_lyoko_device_host_key import restrict_acl


DEVICE = "hgw500bna-qcv2-a2-primary"
EXPECTED_F246_SHA256 = "8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default=DEVICE)
    parser.add_argument("--private-output-root", type=Path, default=Path.home() / ".openmitrastar/devices")
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    if args.device_id != DEVICE:
        raise SystemExit("F247 is pinned to the primary HGW-500BNA-QCv2/A2")

    firmware = args.private_output_root.resolve() / args.device_id / "firmware"
    source = firmware / "f246-device-bound"
    destination = firmware / "f247-device-bound"
    old_base = f"openmitrastar-linux510-f246-{args.device_id}-PRIVATE-NO-FLASH"
    new_base = f"openmitrastar-linux510-f247-{args.device_id}-PRIVATE-NO-FLASH"
    manifest = json.loads((source / "manifest.json").read_text(encoding="ascii"))
    candidate = source / f"{old_base}.webformat.bin"

    if manifest.get("schema") != "openmitrastar.f246-integrated-rxring-package-catalog/v1":
        raise SystemExit("unexpected F246 manifest schema")
    if manifest.get("candidate_eligible") is not False or manifest.get("flash_supported") is not False:
        raise SystemExit("F246 must remain an offline hold")
    if sha256(candidate) != EXPECTED_F246_SHA256 or manifest["artifacts"]["webformat"]["sha256"] != EXPECTED_F246_SHA256:
        raise SystemExit("F246 artifact identity mismatch")
    if manifest["contracts"].get("bootbase") != "PASS" or not manifest["contracts"].get("slot_fit"):
        raise SystemExit("F246 Bootbase contract is not accepted")
    kernel = manifest["integration"]["kernel_contract"]
    if kernel.get("result") != "PASS" or kernel.get("rx_ring_descriptors") != 256 or kernel.get("napi_weight") != 128:
        raise SystemExit("F246 kernel contract mismatch")
    packages = manifest["integration"]["package_catalog"]
    if packages.get("trust") != "runtime-ed25519-plus-sha256" or packages.get("network_fetch") or packages.get("persistent_install"):
        raise SystemExit("F246 package contract mismatch")

    if destination.exists() and not args.replace_existing:
        raise SystemExit(f"refusing to overwrite {destination}")
    if destination.exists():
        if destination.name != "f247-device-bound" or destination.parent != firmware:
            raise SystemExit(f"unsafe replacement target: {destination}")
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    for path in source.iterdir():
        if not path.is_file() or path.name in {"manifest.json", "SHA256SUMS"}:
            continue
        name = path.name.replace(old_base, new_base, 1) if path.name.startswith(old_base) else path.name
        if name == "known_hosts.f246":
            name = "known_hosts.f247"
        shutil.copy2(path, destination / name)

    for value in manifest.get("artifacts", {}).values():
        if isinstance(value, dict) and isinstance(value.get("file"), str):
            value["file"] = value["file"].replace(old_base, new_base, 1)
    manifest.update({
        "schema": "openmitrastar.f247-integrated-physical-test-candidate/v1",
        "classification": "PRIVATE_DEVICE_BOUND_HARDWARE_TEST_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "release_eligible": False,
        "source": {
            "firmware": "F246",
            "artifact_identity": "byte-identical promotion envelope",
            "f246_webformat_sha256": EXPECTED_F246_SHA256,
            "runtime_identity": "lyoko-foundation-4.9-f245-device",
        },
        "promotion": {
            "hardware_actions": {"router": False, "uart": False, "flash": False},
            "normal_write_target": "mtd4/linux_live",
            "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3/linux_safety", "mtd5"],
            "required_campaign": [
                "platform and protected-partition gate",
                "signed package query/install/remove gate",
                "dual-radio transactional control and rollback",
                "three matched 2.4 GHz 32 MiB bidirectional runs",
                "5 GHz 32 MiB plus 120 second continuity",
            ],
        },
        "safety": {
            "normal_write_target": "mtd4/linux_live only",
            "rollback_artifact": "F222 known-good reflash to mtd4",
            "rollback_artifact_sha256": "ab8f8727f3b1c29a312eddb21f1aa5bc9f474d7be91569f57c9230aaf1fc1c21",
            "rollback_tool": "tools/restore_f222_mtd4_from_f247.ps1",
            "rollback_scope": "complete verified F247 slot; interrupted-write recovery remains a manual Bootbase procedure",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd3_status": "preserved but not accepted as automatic recovery because its rootfs mount is unproven",
            "hardware_actions": "none",
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "guarded F247 full physical campaign with AELITA and the configured UART available before flash",
        },
    })
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in destination.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (destination / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    restrict_acl(destination, directory=True)
    for path in destination.iterdir():
        if path.is_file():
            restrict_acl(path, directory=False)

    promoted = destination / f"{new_base}.webformat.bin"
    if sha256(promoted) != EXPECTED_F246_SHA256:
        raise SystemExit("F247 copied artifact differs from F246")
    print(json.dumps({
        "status": "PASS",
        "output": str(destination),
        "candidate": str(promoted),
        "bytes": promoted.stat().st_size,
        "sha256": sha256(promoted),
        "candidate_eligible": True,
        "flash_supported": True,
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
