#!/usr/bin/env python3
"""Fail-closed offline certification for HGW-500BNA-QCv2 backups and flash plans.

The tool is deliberately unable to access MTD devices or issue flash commands.  It
only reads local artifacts.  ``backup-audit`` certifies the captured physical
layout; ``flash-preflight`` additionally requires a hash-pinned eligible candidate
for the inactive live slot while preserving the safety slot as rollback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from make_spi_slot_image import validate_candidate


DEFAULT_BASELINE = Path("work/mission-state/F2_FLASH_BACKUP_BASELINE.json")


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def combined_sha256(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in paths:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()


def parse_env(blob: bytes, region_end: int) -> tuple[dict[str, str], str, bool]:
    if len(blob) < region_end or region_end < 8:
        raise ValueError("environment image is shorter than its CRC region")
    stored = struct.unpack_from("<I", blob)[0]
    calculated = zlib.crc32(blob[4:region_end]) & 0xFFFFFFFF
    entries: dict[str, str] = {}
    for raw in blob[4:region_end].split(b"\0"):
        if not raw:
            break
        if b"=" not in raw:
            raise ValueError("malformed environment entry")
        key, value = raw.split(b"=", 1)
        entries[key.decode("ascii")] = value.decode("ascii")
    return entries, f"{stored:08x}", stored == calculated


def load_candidate_manifest(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("candidate manifest must be a JSON object")
    return raw


def manifest_candidate_hash(manifest: dict[str, Any]) -> str | None:
    for key in ("candidate_sha256", "sha256", "artifact_sha256", "output_sha256"):
        value = manifest.get(key)
        if isinstance(value, str) and len(value) == 64:
            return value.lower()
    artifact = manifest.get("artifact")
    if isinstance(artifact, dict):
        value = artifact.get("sha256")
        if isinstance(value, str) and len(value) == 64:
            return value.lower()
    base_ram_image = manifest.get("base_ram_image")
    if isinstance(base_ram_image, dict):
        value = base_ram_image.get("sha256")
        if isinstance(value, str) and len(value) == 64:
            return value.lower()
    return None


def manifest_candidate_eligible(manifest: dict[str, Any]) -> bool:
    value = manifest.get("candidate_eligible")
    if isinstance(value, bool):
        return value
    classification = manifest.get("classification")
    return classification in {"FLASH-CANDIDATE", "PERSISTENT-FLASH-CANDIDATE"}


def validate_current_read_attestation(
    path: Path,
    baseline: dict[str, Any],
    target: str,
    current_unit_contract: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Validate a separately captured, read-only pre-write snapshot.

    The verifier never creates this attestation because doing so would require
    hardware access.  It only consumes a JSON record produced by a later
    read-only capture step and pins every partition that the flash plan promises
    to preserve.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    schema = raw.get("schema")
    if schema == "openmitrastar.current-flash-read/v2":
        if not isinstance(current_unit_contract, dict):
            return False, "v2 current-unit attestation requires an explicit recovery contract"
        if raw.get("read_only") is not True or raw.get("environment_write_forbidden") is not True:
            return False, "v2 attestation is not read-only/environment-write-forbidden"
        if raw.get("mtd6_included") is not False or raw.get("target_slot") != target:
            return False, "v2 physical layout or target mismatch"
        device = raw.get("device", {})
        expected_device = baseline["device"]
        if (
            device.get("model") != expected_device["model"]
            or device.get("hardware_revision") != expected_device["hardware_revision"]
            or device.get("physical_flash_size") != expected_device["physical_flash_size"]
        ):
            return False, "v2 device identity/flash size mismatch"

        backup_spec = current_unit_contract.get("backup_manifest", {})
        backup_value = raw.get("source_backup_manifest")
        if not isinstance(backup_value, str):
            return False, "v2 source backup manifest missing"
        backup_path = Path(backup_value)
        if not backup_path.is_absolute():
            backup_path = Path.cwd() / backup_path
        if not backup_path.is_file():
            return False, f"v2 source backup missing: {backup_path}"
        backup_hash = digest(backup_path, "sha256")
        if (
            backup_hash != backup_spec.get("sha256")
            or raw.get("source_backup_manifest_sha256") != backup_hash
        ):
            return False, "v2 source backup manifest hash drift"
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        if (
            backup.get("read_only_capture") is not True
            or backup.get("mtd6_included") is not False
            or backup.get("physical_image", {}).get("sha256") != backup_spec.get("physical_image_sha256")
        ):
            return False, "v2 source backup physical contract mismatch"
        expected_hashes = current_unit_contract.get("partition_sha256", {})
        observed_hashes = raw.get("partition_sha256", {})
        backup_hashes = {
            item.get("name"): item.get("sha256") for item in backup.get("partitions", [])
        }
        if observed_hashes != expected_hashes or backup_hashes != expected_hashes:
            return False, "v2 current-unit partition hashes drift"

        expected_env = current_unit_contract.get("environment", {})
        observed_env = raw.get("environment", {})
        if (
            expected_env.get("divergence_accepted") is not True
            or expected_env.get("write_forbidden") is not True
            or observed_env != expected_env
            or observed_env.get("primary", {}).get("crc_valid") is not True
            or observed_env.get("backup", {}).get("crc_valid") is not True
            or observed_env.get("primary", {}).get("bootcmd") != "bootselect"
            or observed_env.get("primary", {}).get("bootselect") != "0"
        ):
            return False, "v2 documented environment divergence contract mismatch"

        rollback_spec = current_unit_contract.get("manual_uart_rollback", {})
        rollback_value = rollback_spec.get("path")
        rollback_path = Path(str(rollback_value))
        if not rollback_path.is_absolute():
            rollback_path = Path.cwd() / rollback_path
        if not rollback_path.is_file() or digest(rollback_path, "sha256") != rollback_spec.get("sha256"):
            return False, "v2 manual UART rollback evidence hash drift"
        rollback_text = rollback_path.read_text(encoding="utf-8", errors="replace")
        missing = [m for m in rollback_spec.get("required_markers", []) if m not in rollback_text]
        observed_rollback = raw.get("manual_uart_rollback", {})
        crc_spec = current_unit_contract.get("partition_crc32", {})
        if (
            missing
            or observed_rollback.get("path") != rollback_spec.get("path")
            or observed_rollback.get("sha256") != rollback_spec.get("sha256")
            or observed_rollback.get("linux_safety_sha256") != expected_hashes.get("linux_safety")
            or observed_rollback.get("linux_safety_crc32") != crc_spec.get("linux_safety")
        ):
            return False, f"v2 manual rollback contract invalid; missing_markers={missing}"
        return True, (
            f"captured_at={raw.get('captured_at')} current_unit=true "
            "env_divergence=documented bootselect=0 rollback=manual-uart-hash-pinned "
            f"linux_safety={expected_hashes.get('linux_safety')}"
        )

    if schema != "openmitrastar.current-flash-read/v1":
        return False, "wrong or missing current-read schema"
    if raw.get("read_only") is not True:
        return False, "attestation is not explicitly read-only"
    device = raw.get("device", {})
    expected_device = baseline["device"]
    if (
        device.get("model") != expected_device["model"]
        or device.get("hardware_revision") != expected_device["hardware_revision"]
        or device.get("physical_flash_size") != expected_device["physical_flash_size"]
    ):
        return False, "device identity/flash size does not match baseline"
    if raw.get("target_slot") != target:
        return False, "attested target slot differs from requested target"
    if raw.get("bootcmd") != baseline["environment"]["bootcmd"]:
        return False, "current bootcmd is not bootselect"
    selected = baseline["environment"]["slot_mapping"].get(str(raw.get("bootselect")))
    if selected != baseline["flash_plan"]["rollback_slot"]:
        return False, f"current selected slot is {selected!r}, not rollback slot"
    hashes = raw.get("partition_sha256", {})
    expected_hashes = {
        part["name"]: part["sha256"]
        for part in baseline["partitions"]
        if part["name"] in baseline["flash_plan"]["preserve"]
    }
    mismatches = {
        name: {"expected": expected, "observed": hashes.get(name)}
        for name, expected in expected_hashes.items()
        if hashes.get(name) != expected
    }
    if mismatches:
        return False, f"preserved partition mismatch: {json.dumps(mismatches, sort_keys=True)}"
    return True, f"captured_at={raw.get('captured_at')} preserve={','.join(sorted(expected_hashes))}"


def certify(
    workspace: Path,
    baseline_path: Path,
    mode: str,
    candidate: Path | None,
    candidate_manifest: Path | None,
    current_read_attestation: Path | None,
    target: str,
) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    dump_dir = workspace / baseline["dump_directory"]
    source_manifest_path = dump_dir / baseline["manifest"]
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_by_idx = {int(item["idx"]): item for item in source_manifest}
    gates: list[Gate] = []

    physical_paths: list[Path] = []
    physical_blobs: dict[str, bytes] = {}
    expected_offset = 0
    for part in baseline["partitions"]:
        path = dump_dir / part["file"]
        physical_paths.append(path)
        exists = path.is_file()
        gates.append(Gate(f"partition-{part['idx']}-exists", exists, str(path)))
        if not exists:
            continue
        size = path.stat().st_size
        md5 = digest(path, "md5")
        sha256 = digest(path, "sha256")
        layout_ok = part["offset"] == expected_offset
        gates.append(
            Gate(
                f"partition-{part['idx']}-layout",
                layout_ok and size == part["size"],
                f"offset=0x{part['offset']:06x} size={size} policy={part['policy']}",
            )
        )
        gates.append(
            Gate(
                f"partition-{part['idx']}-hash",
                md5 == part["md5"] and sha256 == part["sha256"],
                f"md5={md5} sha256={sha256}",
            )
        )
        manifest_entry = source_by_idx.get(int(part["idx"]), {})
        manifest_ok = (
            manifest_entry.get("verified_md5") is True
            and manifest_entry.get("verified_size") is True
            and manifest_entry.get("remote_md5") == part["md5"]
            and manifest_entry.get("local_sha256") == part["sha256"]
        )
        gates.append(
            Gate(
                f"partition-{part['idx']}-live-capture-attestation",
                manifest_ok,
                "local hash/size agrees with manifest's live-device MD5 attestation",
            )
        )
        physical_blobs[part["name"]] = path.read_bytes()
        expected_offset += part["size"]

    flash_size = int(baseline["device"]["physical_flash_size"])
    geometry_ok = expected_offset == flash_size and len(physical_paths) == 6
    gates.append(
        Gate(
            "physical-geometry",
            geometry_ok,
            f"mtd0..mtd5 total={expected_offset} expected={flash_size}",
        )
    )
    if all(path.is_file() for path in physical_paths):
        physical_sha = combined_sha256(physical_paths)
        gates.append(
            Gate(
                "physical-image-sha256",
                physical_sha == baseline["physical_image_sha256"],
                f"sha256={physical_sha}",
            )
        )

    for view in baseline["logical_views"]:
        path = dump_dir / view["file"]
        source = physical_blobs.get(view["source_partition"])
        exists = path.is_file()
        gates.append(Gate(f"logical-{view['idx']}-exists", exists, str(path)))
        if exists and source is not None:
            blob = path.read_bytes()
            duplicate = blob == source[int(view["source_offset"]):]
            gates.append(
                Gate(
                    f"logical-{view['idx']}-is-view-not-physical",
                    duplicate
                    and len(blob) == view["size"]
                    and digest(path, "sha256") == view["sha256"],
                    f"duplicates {view['source_partition']}+0x{view['source_offset']:x}; policy={view['policy']}",
                )
            )

    legacy = baseline["legacy_concatenation"]
    legacy_path = dump_dir / legacy["file"]
    if legacy_path.is_file() and all(path.is_file() for path in physical_paths):
        legacy_blob = legacy_path.read_bytes()
        physical_blob = b"".join(path.read_bytes() for path in physical_paths)
        logical_blob = (dump_dir / baseline["logical_views"][0]["file"]).read_bytes()
        forensic_only = (
            len(legacy_blob) == legacy["size"]
            and digest(legacy_path, "sha256") == legacy["sha256"]
            and legacy_blob[:flash_size] == physical_blob
            and legacy_blob[flash_size:] == logical_blob
            and len(legacy_blob) != flash_size
        )
        gates.append(
            Gate(
                "reject-mtd0-mtd6-as-raw-flash",
                forensic_only,
                f"{legacy_path.name}={len(legacy_blob)} bytes; physical NOR={flash_size}; policy={legacy['policy']}",
            )
        )

    env_spec = baseline["environment"]
    env_primary = physical_blobs.get("uboot_env")
    env_backup = physical_blobs.get("uboot_env_bak")
    env: dict[str, str] = {}
    if env_primary is not None and env_backup is not None:
        primary, primary_crc, primary_crc_ok = parse_env(env_primary, env_spec["crc_region_end"])
        backup, backup_crc, backup_crc_ok = parse_env(env_backup, env_spec["crc_region_end"])
        env = primary
        env_ok = (
            env_primary == env_backup
            and primary == backup
            and primary_crc_ok
            and backup_crc_ok
            and primary_crc == backup_crc == env_spec["stored_crc32"]
            and primary.get("bootcmd") == env_spec["bootcmd"]
            and primary.get("bootselect") == env_spec["bootselect"]
        )
        gates.append(
            Gate(
                "redundant-environment",
                env_ok,
                f"crc={primary_crc} bootcmd={primary.get('bootcmd')} bootselect={primary.get('bootselect')}",
            )
        )

    plan = baseline["flash_plan"]
    selected_slot = env_spec["slot_mapping"].get(env.get("bootselect"), "unknown")
    plan_ok = (
        target == plan["target_slot"]
        and selected_slot == plan["rollback_slot"]
        and target != selected_slot
        and target not in plan["preserve"]
        and plan["rollback_slot"] in plan["preserve"]
    )
    gates.append(
        Gate(
            "inactive-target-and-rollback-plan",
            plan_ok,
            f"selected={selected_slot} target={target} rollback={plan['rollback_slot']} preserve={','.join(plan['preserve'])}",
        )
    )

    recovery = baseline["recovery_evidence"]
    recovery_path = workspace / recovery["log"]
    recovery_text = recovery_path.read_text(encoding="utf-8", errors="replace") if recovery_path.is_file() else ""
    missing_markers = [m for m in recovery["required_markers"] if m not in recovery_text]
    gates.append(
        Gate(
            "uart-bootbase-tftp-ramssh-recovery",
            recovery_path.is_file() and not missing_markers,
            f"log={recovery_path}; missing_markers={missing_markers}",
        )
    )

    candidate_info: dict[str, Any] | None = None
    if mode == "flash-preflight":
        if current_read_attestation is None:
            gates.append(
                Gate(
                    "current-read-only-flash-attestation",
                    False,
                    "flash-preflight requires --current-read-attestation from a fresh read-only capture",
                )
            )
        else:
            current_path = (
                current_read_attestation
                if current_read_attestation.is_absolute()
                else workspace / current_read_attestation
            )
            if not current_path.is_file():
                gates.append(
                    Gate("current-read-only-flash-attestation", False, f"missing {current_path}")
                )
            else:
                current_ok, current_detail = validate_current_read_attestation(
                    current_path, baseline, target
                )
                gates.append(
                    Gate("current-read-only-flash-attestation", current_ok, current_detail)
                )
        if candidate is None or candidate_manifest is None:
            gates.append(
                Gate(
                    "flash-candidate-pinned-and-eligible",
                    False,
                    "flash-preflight requires --candidate and --candidate-manifest",
                )
            )
        else:
            candidate_path = candidate if candidate.is_absolute() else workspace / candidate
            manifest_path = candidate_manifest if candidate_manifest.is_absolute() else workspace / candidate_manifest
            if candidate_path.is_file() and manifest_path.is_file():
                candidate_sha = digest(candidate_path, "sha256")
                manifest = load_candidate_manifest(manifest_path)
                pinned_sha = manifest_candidate_hash(manifest)
                eligible = manifest_candidate_eligible(manifest)
                slot_size = next(p["size"] for p in baseline["partitions"] if p["name"] == target)
                try:
                    format_info = validate_candidate(candidate_path.read_bytes())
                    format_ok = True
                    format_error = None
                except ValueError as exc:
                    format_info = None
                    format_ok = False
                    format_error = str(exc)
                candidate_info = {
                    "path": str(candidate_path),
                    "size": candidate_path.stat().st_size,
                    "sha256": candidate_sha,
                    "manifest": str(manifest_path),
                    "manifest_sha256": pinned_sha,
                    "candidate_eligible": eligible,
                    "format_ok": format_ok,
                    "format": format_info,
                    "format_error": format_error,
                }
                gates.append(
                    Gate(
                        "flash-candidate-pinned-and-eligible",
                        candidate_sha == pinned_sha
                        and eligible
                        and format_ok
                        and 0 < candidate_path.stat().st_size <= slot_size,
                        json.dumps(candidate_info, sort_keys=True),
                    )
                )
            else:
                gates.append(
                    Gate(
                        "flash-candidate-pinned-and-eligible",
                        False,
                        f"missing candidate={candidate_path} or manifest={manifest_path}",
                    )
                )

    flash_only_gates = {
        "current-read-only-flash-attestation",
        "flash-candidate-pinned-and-eligible",
    }
    backup_gate_names = {gate.name for gate in gates if gate.name not in flash_only_gates}
    backup_certified = all(gate.passed for gate in gates if gate.name in backup_gate_names)
    flash_ready = mode == "flash-preflight" and all(gate.passed for gate in gates)
    return {
        "schema": "openmitrastar.flash-backup-preflight/v1",
        "mode": mode,
        "read_only": True,
        "hardware_access": False,
        "flash_commands_present": False,
        "device": baseline["device"],
        "target_slot": target,
        "rollback_slot": plan["rollback_slot"],
        "backup_certified": backup_certified,
        "flash_ready": flash_ready,
        "rollback_transport_proven": next(
            gate.passed for gate in gates if gate.name == "uart-bootbase-tftp-ramssh-recovery"
        ),
        "post_flash_rollback_executed": False,
        "candidate": candidate_info,
        "gates": [gate.as_dict() for gate in gates],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--mode", choices=("backup-audit", "flash-preflight"), default="backup-audit")
    parser.add_argument("--target", choices=("linux_live", "linux_safety"), default="linux_live")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--current-read-attestation", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)

    workspace = args.workspace.resolve()
    baseline = args.baseline
    if not baseline.is_absolute():
        baseline = workspace / baseline
    report = certify(
        workspace,
        baseline,
        args.mode,
        args.candidate,
        args.candidate_manifest,
        args.current_read_attestation,
        args.target,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        output = args.json_out if args.json_out.is_absolute() else workspace / args.json_out
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if (report["backup_certified"] if args.mode == "backup-audit" else report["flash_ready"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
