#!/usr/bin/env python3
"""Create a non-executing, hash-bound F194 recovery provisioning contract."""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "work/mission-state/q3-recovery-f194-linux510-safety-slot/build"
MANIFEST = BUILD / "manifest.json"
BOOTBASE = BUILD / "safety-bootbase-contract.json"
RECOVERY_EVIDENCE = ROOT / "outputs/recovery/mtd3-current-evidence-20260901/result.json"
F170_FLASH = ROOT / "work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build/flash-one-shot-20260901T111746Z/result.json"
CURRENT_STATE = ROOT / "work/mission-state/CURRENT_STATE.json"
DEFAULT_OUTPUT = ROOT / "outputs/recovery/f194-provisioning-contract-20260901/contract.json"


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crc32(path: Path) -> str:
    value = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value = binascii.crc32(chunk, value)
    return f"{value & 0xffffffff:08x}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = load(MANIFEST)
    bootbase = load(BOOTBASE)
    recovery = load(RECOVERY_EVIDENCE)
    f170 = load(F170_FLASH)
    current = load(CURRENT_STATE)

    candidate = BUILD / manifest["artifacts"]["webformat"]["file"]
    full_slot = BUILD / manifest["artifacts"]["safety_full_slot"]["file"]
    expected_candidate = manifest["artifacts"]["webformat"]
    expected_slot = manifest["artifacts"]["safety_full_slot"]
    candidate_bytes = candidate.read_bytes()
    slot_bytes = full_slot.read_bytes()

    checks = {
        "candidate_exists": candidate.is_file(),
        "candidate_size": len(candidate_bytes) == expected_candidate["bytes"],
        "candidate_sha256": sha256(candidate) == expected_candidate["sha256"],
        "candidate_crc32": crc32(candidate) == expected_candidate["crc32"],
        "full_slot_exists": full_slot.is_file(),
        "full_slot_size": len(slot_bytes) == 0x7A0000 == expected_slot["bytes"],
        "full_slot_sha256": sha256(full_slot) == expected_slot["sha256"],
        "full_slot_crc32": crc32(full_slot) == manifest["artifacts"]["full_slot"]["crc32"],
        "candidate_is_slot_prefix": slot_bytes[: len(candidate_bytes)] == candidate_bytes,
        "remaining_slot_is_erased_ff": all(value == 0xFF for value in slot_bytes[len(candidate_bytes) :]),
        "manifest_targets_linux_safety": manifest.get("target_slot") == "mtd3/linux_safety",
        "bootbase_contract_pass": bootbase.get("result") == "PASS",
        "bootbase_selects_safety": bootbase.get("decision", {}).get("selected_slot") == "linux_safety",
        "bootbase_fallback_is_live": bootbase.get("decision", {}).get("fallback_slot") == "linux_live",
        "current_mtd3_is_known_no_go": recovery.get("status") == "RECOVERY_NO_GO_ROOTFS_MOUNT_FAILURE",
        "current_mtd3_backup_matches_flash_attestation": recovery.get("mtd3", {}).get("sha256") == f170.get("protected_partitions", {}).get("mtd3"),
        "current_live_is_f170": current.get("physical", {}).get("firmware") == "lyoko-foundation-1.0-f170",
        "current_live_target_is_mtd4": current.get("physical", {}).get("normal_write_target") == "mtd4/linux_live",
    }
    all_checks_pass = all(checks.values())
    acknowledgement = (
        f"OPENMITRASTAR_EXCEPTION_F194_MTD3_{sha256(full_slot)[:8].upper()}_"
        f"FROM_{recovery['mtd3']['sha256'][:8].upper()}"
    )
    contract = {
        "schema": "openmitrastar.f194-recovery-provisioning-contract/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "WAITING_EXPLICIT_EXCEPTION_AUTHORIZATION" if all_checks_pass else "BLOCKED_PREFLIGHT_FAILED",
        "hardware_actions_performed": {"uart": False, "reboot": False, "flash": False, "bootenv_write": False},
        "authorization": {
            "granted": False,
            "required_exact_acknowledgement": acknowledgement,
            "scope": "one exceptional replacement of physical mtd3/linux_safety only",
        },
        "target": {
            "model": "HGW-500BNA-QCv2 A2",
            "partition": "mtd3/linux_safety",
            "offset": "0x00040000",
            "slot_bytes": 0x7A0000,
            "candidate_bytes": len(candidate_bytes),
            "candidate_sha256": sha256(candidate),
            "candidate_crc32": crc32(candidate),
            "full_slot_sha256": sha256(full_slot),
            "full_slot_crc32": crc32(full_slot),
        },
        "current_recovery_backup": {
            "bytes": recovery["mtd3"]["bytes"],
            "sha256": recovery["mtd3"]["sha256"],
            "status": recovery["status"],
            "evidence": str(RECOVERY_EVIDENCE.relative_to(ROOT)).replace("\\", "/"),
        },
        "protected_partitions": {
            name: digest for name, digest in f170["protected_partitions"].items() if name != "status" and name != "mtd3"
        },
        "boot_policy": {
            "boot_environment_write_allowed": False,
            "manual_test_selection": "Bootbase ATGO",
            "expected_test_slot": "linux_safety",
            "expected_fallback_slot": "linux_live",
            "normal_iteration_target_after_test": "mtd4/linux_live",
        },
        "required_evidence_after_authorized_operation": [
            "complete UART transcript",
            "pre-write protected partition hashes",
            "mtd3 full-slot readback SHA-256 and CRC32",
            "Linux 5.10 boot from rootfs_safety",
            "Ethernet management and SSH reachability",
            "manual return to mtd4 followed by a cold boot",
            "post-test protected partition hashes",
        ],
        "checks": checks,
        "decision": "NO_EXECUTOR_EMITTED_UNTIL_EXPLICIT_AUTHORIZATION",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2) + "\n", encoding="ascii")
    print(json.dumps(contract, indent=2))
    return 0 if all_checks_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
