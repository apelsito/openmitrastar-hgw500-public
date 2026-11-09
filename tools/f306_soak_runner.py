#!/usr/bin/env python3
"""Run or resume a strict 6 h/24 h F306 sequential dual-radio soak.

The orchestration reuses the physically exercised F301 soak engine while
pinning the exact F306 image and the SSH-v2 client runners.  A new evidence
directory may be seeded from a previous F306 run without modifying the source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import aelita_ssh_policy as ssh_policy
import run_f301_sequential_dual_radio_soak as base


ROOT = Path(__file__).resolve().parents[1]
DEVICE = "hgw500bna-qcv2-a2-primary"
BUILD = Path.home() / f".openmitrastar/devices/{DEVICE}/firmware/f306-device-bound"
KNOWN_HOSTS = BUILD / "known_hosts.f306"
MANIFEST = BUILD / "manifest.json"
EXPECTED_VERSION = "lyoko-foundation-6.7.3-f306-unified-product-device"
EXPECTED_SHA256 = "a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2"
ACK = "OPENMITRASTAR_F306_SEQUENTIAL_DUAL_RADIO_SOAK"
RADIO5_ACK = "OPENMITRASTAR_F306_5G_AELITA_TRAFFIC"
PLAN_SCHEMA = "openmitrastar.f306-sequential-dual-radio-soak-plan/v1"
CHECKPOINT_SCHEMA = "openmitrastar.f306-sequential-dual-radio-soak-checkpoint/v1"
RESULT_SCHEMA = "openmitrastar.f306-sequential-dual-radio-soak/v1"
CYCLE_SCHEMA = "openmitrastar.f306-sequential-dual-radio-cycle/v1"
CYCLE_STATE_SCHEMA = "openmitrastar.f306-sequential-dual-radio-cycle-state/v1"
INVOCATION_SCHEMA = "openmitrastar.f306-sequential-dual-radio-soak-invocation/v1"
SEED_SCHEMA = "openmitrastar.f306-soak-continuation-seed/v1"
AELITA_KNOWN_HOSTS = (
    ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/known_hosts"
)

ORIGINAL_PARSER = base.parser
ORIGINAL_PLAN = base.immutable_plan
ORIGINAL_VALIDATE_RESUME = base.validate_resume

POLICY_KEYS = (
    "aelita_known_hosts_file",
    "aelita_host_key_mode",
    "aelita_fingerprint_enforced",
    "aelita_ssh_connect_timeout",
)
SEED_STABLE_KEYS = (
    "schema",
    "mode",
    "required_firmware",
    "candidate_file",
    "candidate_sha256",
    "router_host",
    "oracle_host",
    "oracle_user",
    "controller_url",
    "soak_seconds_per_band",
    "cycle_pause_seconds",
    "snapshot_attempts",
    "snapshot_retry_seconds",
    "radio2_runner",
    "radio5_runner",
    "radio5_profile",
    "radio5_ack",
    "restore_ssid",
    *POLICY_KEYS,
)


def configure_base() -> None:
    base.BUILD = BUILD
    base.KNOWN_HOSTS = KNOWN_HOSTS
    base.MANIFEST = MANIFEST
    base.EXPECTED_VERSION = EXPECTED_VERSION
    base.EXPECTED_SHA256 = EXPECTED_SHA256
    base.ACK = ACK
    base.RADIO5_ACK = RADIO5_ACK
    base.PLAN_SCHEMA = PLAN_SCHEMA
    base.CHECKPOINT_SCHEMA = CHECKPOINT_SCHEMA
    base.RESULT_SCHEMA = RESULT_SCHEMA
    base.CYCLE_SCHEMA = CYCLE_SCHEMA
    base.CYCLE_STATE_SCHEMA = CYCLE_STATE_SCHEMA
    base.INVOCATION_SCHEMA = INVOCATION_SCHEMA
    base.LOCK_OWNER = "f306-sequential-dual-radio-soak"
    base.OUTPUT_PREFIX = "f306-sequential-dual-radio"
    base.FIRMWARE_LABEL = "F306"


def parser() -> argparse.ArgumentParser:
    result = ORIGINAL_PARSER()
    for action in result._actions:
        if action.dest == "duration_hours":
            action.choices = (6.0, 24.0)
            action.default = 6.0
            action.help = "certification duration; exactly 6 or 24 hours"
            break
    result.add_argument(
        "--seed-from",
        type=Path,
        help="start a new evidence directory from a prior F306 checkpoint/result",
    )
    result.add_argument(
        "--seed-reason",
        default="explicit F306 soak continuation",
        help="non-secret reason recorded in seed.json",
    )
    ssh_policy.add_policy_arguments(result)
    return result


def policy_cli(args: argparse.Namespace) -> list[str]:
    result = [
        "--aelita-known-hosts", str(args.aelita_known_hosts),
        "--aelita-host-key-mode", args.aelita_host_key_mode,
        "--aelita-ssh-connect-timeout", str(args.aelita_ssh_connect_timeout),
    ]
    if args.aelita_host_key_sha256:
        result.extend(("--aelita-host-key-sha256", args.aelita_host_key_sha256))
    return result


def radio2_command(args: argparse.Namespace, output_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tools/run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py"),
        *policy_cli(args),
        "--router-host", args.router_host,
        "--router-known-hosts", str(KNOWN_HOSTS),
        "--oracle-host", args.oracle_host,
        "--oracle-user", args.oracle_user,
        "--controller-url", args.controller_url,
        "--traffic-direction", "both",
        "--interval", "3",
        "--wait-result", str(args.soak_seconds + 240),
        "--child-timeout", str(args.soak_seconds + 180),
        "--recovery-window", "120",
        "--restore-watchdog-minutes", "5",
        "--soak-seconds", str(args.soak_seconds),
        "--output-dir", str(output_dir),
    ]


def radio5_command(args: argparse.Namespace, output_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tools/run_f293_5g_aelita_traffic_ssh_v2.py"),
        *policy_cli(args),
        "--router-known-hosts", str(KNOWN_HOSTS),
        "--profile", "f306",
        "--execute", "--ack", RADIO5_ACK,
        "--router-host", args.router_host,
        "--oracle-host", args.oracle_host,
        "--oracle-user", args.oracle_user,
        "--controller-url", args.controller_url,
        "--soak-seconds", str(args.soak_seconds),
        "--output-dir", str(output_dir),
    ]


def immutable_plan(
    args: argparse.Namespace, candidate: Path, candidate_hash: str
) -> dict[str, object]:
    return {
        "schema": PLAN_SCHEMA,
        "mode": "execute" if args.execute else "dry-run",
        "required_firmware": EXPECTED_VERSION,
        "candidate_file": candidate.name,
        "candidate_sha256": candidate_hash,
        "candidate_matches": candidate_hash == EXPECTED_SHA256,
        "known_hosts_file": KNOWN_HOSTS.name,
        "known_hosts_present": KNOWN_HOSTS.is_file(),
        "router_host": args.router_host,
        "oracle_host": args.oracle_host,
        "oracle_user": args.oracle_user,
        "controller_url": args.controller_url,
        "duration_hours": args.duration_hours,
        "target_duration_seconds": args.duration_hours * 3600,
        "certification_duration": "6h" if args.duration_hours == 6.0 else "24h",
        "soak_seconds_per_band": args.soak_seconds,
        "cycle_pause_seconds": args.cycle_pause_seconds,
        "snapshot_attempts": args.snapshot_attempts,
        "snapshot_retry_seconds": args.snapshot_retry_seconds,
        "radio2_runner": "tools/run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py",
        "radio5_runner": "tools/run_f293_5g_aelita_traffic_ssh_v2.py",
        "radio5_profile": "f306",
        "radio5_ack": RADIO5_ACK,
        "client_mode": "single-AELITA-sequential",
        "simultaneous_dual_radio": False,
        "restore_ssid": "MOVISTAR-WIFI6-A348",
        "hardware_preflight": "DEFERRED_TO_EXECUTE" if not args.execute else "REQUIRED",
        "hardware_actions_performed": False,
        "flash": False,
        "mtd_writes": False,
        "aelita_known_hosts_file": str(args.aelita_known_hosts),
        "aelita_known_hosts_present": args.aelita_known_hosts.is_file(),
        "aelita_host_key_mode": args.aelita_host_key_mode,
        "aelita_fingerprint_enforced": bool(args.aelita_host_key_sha256),
        "aelita_ssh_connect_timeout": args.aelita_ssh_connect_timeout,
        "seed_source": str(args.seed_from.resolve()) if args.seed_from else None,
        "seed_lineage_required": bool(args.seed_from),
    }


def summarize(
    cycles: list[dict[str, object]],
    started: base.datetime,
    updated: base.datetime,
    active_elapsed_seconds: float,
    target_duration_seconds: float,
    forced_status: str | None = None,
) -> dict[str, object]:
    result = base.summarize(
        cycles,
        started,
        updated,
        active_elapsed_seconds,
        target_duration_seconds,
        forced_status,
    )
    result["schema"] = RESULT_SCHEMA
    return result


def checkpoint_payload(
    cycles: list[dict[str, object]],
    started: base.datetime,
    active_elapsed: float,
    target_seconds: float,
    status: str,
) -> dict[str, object]:
    payload = summarize(cycles, started, base.utcnow(), active_elapsed, target_seconds, status)
    payload["schema"] = CHECKPOINT_SCHEMA
    payload["next_cycle"] = len(cycles) + 1
    return payload


def validate_resume(output_dir: Path, expected_plan: dict[str, object]):
    previous, cycles, started, elapsed = ORIGINAL_VALIDATE_RESUME(output_dir, expected_plan)
    mismatches = [key for key in POLICY_KEYS if previous.get(key) != expected_plan.get(key)]
    if mismatches:
        raise RuntimeError("resume SSH policy mismatch: " + ", ".join(mismatches))
    seed = output_dir / "seed.json"
    expected_seed = bool(previous.get("seed_lineage_required"))
    if seed.is_file() != expected_seed:
        raise RuntimeError("resume seed lineage presence mismatch")
    if seed.is_file() and base.read_json(seed).get("schema") != SEED_SCHEMA:
        raise RuntimeError("resume seed schema mismatch")
    return previous, cycles, started, elapsed


def sha256_json(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("ascii")).hexdigest()


def _source_terminal_state(source: Path) -> tuple[dict[str, Any], str]:
    result = source / "result.json"
    checkpoint = source / "checkpoint.json"
    if result.is_file():
        return base.read_json(result), "result.json"
    if checkpoint.is_file():
        return base.read_json(checkpoint), "checkpoint.json"
    raise RuntimeError("seed source requires checkpoint.json or result.json")


def load_seed_cycles(source: Path) -> list[dict[str, object]]:
    directories = sorted(source.glob("cycle-[0-9][0-9][0-9]"))
    cycles: list[dict[str, object]] = []
    incomplete_seen = False
    for expected, directory in enumerate(directories, start=1):
        if directory.name != f"cycle-{expected:03d}":
            raise RuntimeError("seed source cycle directories are not contiguous")
        result_path = directory / "cycle.json"
        if not result_path.is_file():
            incomplete_seen = True
            continue
        if incomplete_seen:
            raise RuntimeError("seed source has a PASS cycle after an incomplete cycle")
        result = base.read_json(result_path)
        if (
            result.get("schema") != CYCLE_SCHEMA
            or result.get("cycle") != expected
            or result.get("status") != "PASS"
        ):
            raise RuntimeError(f"seed source cycle {expected} is not a matching F306 PASS")
        cycles.append(result)
    return cycles


def inspect_seed_source(
    source: Path, expected_plan: dict[str, object]
) -> tuple[dict[str, Any], list[dict[str, object]], dict[str, Any]]:
    source = source.resolve(strict=True)
    plan_path = source / "plan.json"
    checkpoint_path = source / "checkpoint.json"
    if not plan_path.is_file() or not checkpoint_path.is_file():
        raise RuntimeError("seed source requires plan.json and checkpoint.json")
    plan = base.read_json(plan_path)
    checkpoint = base.read_json(checkpoint_path)
    state, state_file = _source_terminal_state(source)
    if plan.get("schema") != PLAN_SCHEMA:
        raise RuntimeError("seed source plan schema mismatch")
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        raise RuntimeError("seed source checkpoint schema mismatch")
    mismatches = [key for key in SEED_STABLE_KEYS if plan.get(key) != expected_plan.get(key)]
    if mismatches:
        raise RuntimeError("seed source plan mismatch: " + ", ".join(mismatches))
    if plan.get("required_firmware") != EXPECTED_VERSION or plan.get("candidate_sha256") != EXPECTED_SHA256:
        raise RuntimeError("seed source is not the exact F306 artifact")
    cycles = load_seed_cycles(source)
    if int(state.get("cycles_completed") or 0) != len(cycles):
        raise RuntimeError("seed source cycle count mismatch")
    elapsed = float(state.get("active_elapsed_seconds") or 0)
    target = float(expected_plan["target_duration_seconds"])
    if elapsed < 0 or elapsed >= target:
        raise RuntimeError("seed source already reaches or exceeds the requested target")
    metadata = {
        "source": str(source),
        "source_status": state.get("status"),
        "source_error": state.get("error"),
        "source_state_file": state_file,
        "source_plan_sha256": sha256_json(plan),
        "source_state_sha256": sha256_json(state),
        "imported_cycles": len(cycles),
        "imported_active_elapsed_seconds": elapsed,
        "source_target_duration_seconds": float(plan.get("target_duration_seconds") or 0),
        "started_at": checkpoint.get("started_at"),
    }
    return plan, cycles, metadata


def prepare_seed(
    output_dir: Path,
    source: Path,
    plan: dict[str, object],
    reason: str,
) -> dict[str, Any]:
    _, cycles, metadata = inspect_seed_source(source, plan)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError("refusing to overwrite seed destination")
    output_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, len(cycles) + 1):
        shutil.copytree(source.resolve() / f"cycle-{index:03d}", output_dir / f"cycle-{index:03d}")
    base.atomic_write_json(output_dir / "plan.json", plan)
    started = base.datetime.fromisoformat(str(metadata["started_at"]))
    checkpoint = checkpoint_payload(
        cycles,
        started,
        float(metadata["imported_active_elapsed_seconds"]),
        float(plan["target_duration_seconds"]),
        "PAUSED",
    )
    base.atomic_write_json(output_dir / "checkpoint.json", checkpoint)
    seed = {
        "schema": SEED_SCHEMA,
        **metadata,
        "reason": reason,
        "target_duration_seconds": float(plan["target_duration_seconds"]),
        "source_modified": False,
        "hardware_actions_performed": False,
        "flash": False,
        "mtd_writes": False,
    }
    base.atomic_write_json(output_dir / "seed.json", seed)
    return seed


def validate_local_policy(args: argparse.Namespace) -> None:
    if args.aelita_known_hosts.is_file():
        ssh_policy.ensure_known_host(
            args.oracle_host,
            args.aelita_known_hosts,
            mode="pinned",
            expected_fingerprint=args.aelita_host_key_sha256,
        )
    elif args.aelita_host_key_mode == "pinned":
        raise SystemExit("pinned AELITA known_hosts file is missing")


def forwarded_args(args: argparse.Namespace, *, force_resume: bool = False) -> list[str]:
    result = [
        *([] if not args.execute else ["--execute"]),
        *([] if not args.ack else ["--ack", args.ack]),
        "--router-host", args.router_host,
        "--oracle-host", args.oracle_host,
        "--oracle-user", args.oracle_user,
        "--controller-url", args.controller_url,
        "--duration-hours", str(args.duration_hours),
        "--soak-seconds", str(args.soak_seconds),
        "--cycle-pause-seconds", str(args.cycle_pause_seconds),
        "--max-cycles", str(args.max_cycles),
        "--snapshot-attempts", str(args.snapshot_attempts),
        "--snapshot-retry-seconds", str(args.snapshot_retry_seconds),
        *([] if not (args.resume or force_resume) else ["--resume"]),
        *([] if args.output_dir is None else ["--output-dir", str(args.output_dir)]),
        "--aelita-known-hosts", str(args.aelita_known_hosts),
        "--aelita-host-key-mode", args.aelita_host_key_mode,
        "--aelita-ssh-connect-timeout", str(args.aelita_ssh_connect_timeout),
        *([] if not args.aelita_host_key_sha256 else [
            "--aelita-host-key-sha256", args.aelita_host_key_sha256
        ]),
        *([] if args.seed_from is None else ["--seed-from", str(args.seed_from)]),
        "--seed-reason", args.seed_reason,
    ]
    return result


def main(argv: list[str] | None = None) -> int:
    configure_base()
    args = parser().parse_args(argv)
    if args.resume and args.seed_from:
        raise SystemExit("--resume and --seed-from are mutually exclusive")
    if args.aelita_known_hosts is None:
        args.aelita_known_hosts = AELITA_KNOWN_HOSTS
    args.aelita_known_hosts = args.aelita_known_hosts.resolve()
    validate_local_policy(args)

    base.parser = parser
    base.immutable_plan = immutable_plan
    base.validate_resume = validate_resume
    base.radio2_command = radio2_command
    base.radio5_command = radio5_command

    force_resume = False
    if args.execute and args.seed_from:
        if args.output_dir is None:
            raise SystemExit("--seed-from requires an explicit --output-dir")
        manifest = base.read_json(MANIFEST)
        artifact = manifest.get("artifacts", {}).get("webformat", {})
        candidate = BUILD / str(artifact.get("file") or "")
        plan = immutable_plan(args, candidate, base.sha256(candidate))
        try:
            prepare_seed(args.output_dir.resolve(), args.seed_from, plan, args.seed_reason)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        force_resume = True
    elif args.seed_from:
        manifest = base.read_json(MANIFEST)
        artifact = manifest.get("artifacts", {}).get("webformat", {})
        candidate = BUILD / str(artifact.get("file") or "")
        plan = immutable_plan(args, candidate, base.sha256(candidate))
        try:
            _, _, metadata = inspect_seed_source(args.seed_from, plan)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        plan["seed_preview"] = metadata

    return base.main(forwarded_args(args, force_resume=force_resume))


if __name__ == "__main__":
    raise SystemExit(main())
