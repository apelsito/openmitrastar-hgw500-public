#!/usr/bin/env python3
"""Create the flash-readiness attestation from a fresh physical UART backup."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from openmitrastar_flash_backup_preflight import (
    parse_env,
    validate_current_read_attestation,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-manifest", type=Path, required=True)
    parser.add_argument(
        "--baseline", type=Path,
        default=Path("work/mission-state/F2_FLASH_BACKUP_BASELINE.json"),
    )
    parser.add_argument(
        "--contract", type=Path,
        default=Path("work/mission-state/F2_Q1_FULL_FLASH_CANDIDATE_INPUT_CONTRACT.json"),
    )
    parser.add_argument("--allow-documented-env-divergence", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    backup_path = args.backup_manifest.resolve()
    baseline_path = args.baseline.resolve()
    contract = json.loads(args.contract.resolve().read_text(encoding="utf-8"))
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    validation = backup.get("validation", {})
    if (
        backup.get("read_only_capture") is not True
        or backup.get("mtd6_included") is not False
        or validation.get("all_partition_sizes_exact") is not True
        or validation.get("all_physical_partitions_present") is not True
        or validation.get("physical_size_exact") is not True
    ):
        raise ValueError("backup manifest does not prove a complete read-only physical capture")

    parts = {str(item["name"]): item for item in backup["partitions"]}
    env_spec = baseline["environment"]
    env_values = []
    env_records = []
    for name in ("uboot_env", "uboot_env_bak"):
        part = parts[name]
        path = backup_path.parent / str(part["file"])
        if not path.is_file() or sha256(path) != part["sha256"]:
            raise ValueError(f"fresh partition artifact/hash missing: {name}")
        values, stored_crc, crc_ok = parse_env(path.read_bytes(), env_spec["crc_region_end"])
        if not crc_ok:
            raise ValueError(f"fresh environment CRC invalid: {name}")
        env_values.append(values)
        env_records.append({
            "crc32": stored_crc,
            "crc_valid": crc_ok,
            "bootcmd": values.get("bootcmd"),
            "bootselect": values.get("bootselect"),
        })
    divergent = env_values[0] != env_values[1]
    current_unit = contract.get("current_unit_recovery_contract")
    if divergent and not args.allow_documented_env_divergence:
        raise ValueError("fresh redundant environments differ")
    if divergent:
        if not isinstance(current_unit, dict):
            raise ValueError("documented environment divergence has no current-unit contract")
        expected_env = current_unit.get("environment", {})
        observed_env = {
            "divergence_accepted": True,
            "write_forbidden": True,
            "primary": env_records[0],
            "backup": env_records[1],
        }
        if observed_env != expected_env:
            raise ValueError("fresh environment divergence differs from pinned current-unit contract")
    else:
        observed_env = {
            "divergence_accepted": False,
            "write_forbidden": True,
            "primary": env_records[0],
            "backup": env_records[1],
        }
    env = env_values[0]

    schema = "openmitrastar.current-flash-read/v2" if divergent else "openmitrastar.current-flash-read/v1"
    attestation = {
        "schema": schema,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "capture_transport": "Linux 5.10 OMSPIRO read-only over authenticated SSH",
        "source_backup_manifest": str(backup_path),
        "source_backup_manifest_sha256": sha256(backup_path),
        "device": baseline["device"],
        "target_slot": baseline["flash_plan"]["target_slot"],
        "bootcmd": env.get("bootcmd"),
        "bootselect": env.get("bootselect"),
        "partition_sha256": {
            name: str(part["sha256"]) for name, part in parts.items()
        },
        "mtd6_included": False,
    }
    if divergent:
        expected_hashes = current_unit.get("partition_sha256", {})
        if attestation["partition_sha256"] != expected_hashes:
            raise ValueError("fresh partition hashes differ from pinned current-unit contract")
        rollback = current_unit.get("manual_uart_rollback", {})
        rollback_path = Path(str(rollback.get("path", ""))).resolve()
        if not rollback_path.is_file() or sha256(rollback_path) != rollback.get("sha256"):
            raise ValueError("manual UART rollback evidence hash drift")
        rollback_text = rollback_path.read_text(encoding="utf-8", errors="replace")
        missing = [m for m in rollback.get("required_markers", []) if m not in rollback_text]
        if missing:
            raise ValueError(f"manual UART rollback markers missing: {missing}")
        attestation.update({
            "environment_write_forbidden": True,
            "environment": observed_env,
            "manual_uart_rollback": {
                "path": rollback.get("path"),
                "sha256": rollback.get("sha256"),
                "linux_safety_sha256": expected_hashes.get("linux_safety"),
                "linux_safety_crc32": current_unit.get("partition_crc32", {}).get("linux_safety"),
            },
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(attestation, indent=2) + "\n", encoding="utf-8")
    ok, detail = validate_current_read_attestation(
        args.output, baseline, "linux_live", current_unit if divergent else None
    )
    if not ok:
        args.output.unlink(missing_ok=True)
        raise ValueError(detail)
    print(f"CURRENT_FLASH_READ_PASS output={args.output.resolve()} detail={detail}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"CURRENT_FLASH_READ_FAIL error={exc}", file=sys.stderr)
        raise SystemExit(1)
