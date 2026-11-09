#!/usr/bin/env python3
"""F301 soak using persistent, optionally pinned SSH identity for AELITA."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import aelita_ssh_policy as ssh_policy
import run_f301_sequential_dual_radio_soak as base


AELITA_KNOWN_HOSTS = (
    base.ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/known_hosts"
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


def parser() -> argparse.ArgumentParser:
    result = ORIGINAL_PARSER()
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
        str(base.ROOT / "tools/run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py"),
        *policy_cli(args),
        "--router-host", args.router_host,
        "--router-known-hosts", str(base.KNOWN_HOSTS),
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
        str(base.ROOT / "tools/run_f293_5g_aelita_traffic_ssh_v2.py"),
        *policy_cli(args),
        "--router-known-hosts", str(base.KNOWN_HOSTS),
        "--profile", "f301",
        "--execute", "--ack", base.RADIO5_ACK,
        "--router-host", args.router_host,
        "--oracle-host", args.oracle_host,
        "--oracle-user", args.oracle_user,
        "--controller-url", args.controller_url,
        "--soak-seconds", str(args.soak_seconds),
        "--output-dir", str(output_dir),
    ]


def immutable_plan(args: argparse.Namespace, candidate: Path, candidate_hash: str) -> dict[str, object]:
    result = ORIGINAL_PLAN(args, candidate, candidate_hash)
    result.update(
        {
            "schema": "openmitrastar.f301-sequential-dual-radio-soak-plan/v2",
            "aelita_known_hosts_file": str(args.aelita_known_hosts),
            "aelita_known_hosts_present": args.aelita_known_hosts.is_file(),
            "aelita_host_key_mode": args.aelita_host_key_mode,
            "aelita_fingerprint_enforced": bool(args.aelita_host_key_sha256),
            "aelita_ssh_connect_timeout": args.aelita_ssh_connect_timeout,
            "radio2_runner": "tools/run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py",
            "radio5_runner": "tools/run_f293_5g_aelita_traffic_ssh_v2.py",
        }
    )
    return result


def validate_resume(output_dir: Path, expected_plan: dict[str, object]):
    previous, cycles, started, elapsed = ORIGINAL_VALIDATE_RESUME(output_dir, expected_plan)
    mismatches = [key for key in POLICY_KEYS if previous.get(key) != expected_plan.get(key)]
    if mismatches:
        raise RuntimeError("resume SSH policy mismatch: " + ", ".join(mismatches))
    return previous, cycles, started, elapsed


def validate_local_policy(args: argparse.Namespace) -> None:
    path = args.aelita_known_hosts
    if path.is_file():
        ssh_policy.ensure_known_host(
            args.oracle_host,
            path,
            mode="pinned",
            expected_fingerprint=args.aelita_host_key_sha256,
        )
    elif args.aelita_host_key_mode == "pinned":
        raise SystemExit("pinned AELITA known_hosts file is missing")


def main(argv: list[str] | None = None) -> int:
    parsed = parser().parse_args(argv)
    if parsed.aelita_known_hosts is None:
        parsed.aelita_known_hosts = AELITA_KNOWN_HOSTS
    parsed.aelita_known_hosts = parsed.aelita_known_hosts.resolve()
    validate_local_policy(parsed)

    base.parser = parser
    base.immutable_plan = immutable_plan
    base.validate_resume = validate_resume
    base.radio2_command = radio2_command
    base.radio5_command = radio5_command
    return base.main([
        *([] if not parsed.execute else ["--execute"]),
        *([] if not parsed.ack else ["--ack", parsed.ack]),
        "--router-host", parsed.router_host,
        "--oracle-host", parsed.oracle_host,
        "--oracle-user", parsed.oracle_user,
        "--controller-url", parsed.controller_url,
        "--duration-hours", str(parsed.duration_hours),
        "--soak-seconds", str(parsed.soak_seconds),
        "--cycle-pause-seconds", str(parsed.cycle_pause_seconds),
        "--max-cycles", str(parsed.max_cycles),
        "--snapshot-attempts", str(parsed.snapshot_attempts),
        "--snapshot-retry-seconds", str(parsed.snapshot_retry_seconds),
        *([] if not parsed.resume else ["--resume"]),
        *([] if parsed.output_dir is None else ["--output-dir", str(parsed.output_dir)]),
        "--aelita-known-hosts", str(parsed.aelita_known_hosts),
        "--aelita-host-key-mode", parsed.aelita_host_key_mode,
        "--aelita-ssh-connect-timeout", str(parsed.aelita_ssh_connect_timeout),
        *(
            []
            if not parsed.aelita_host_key_sha256
            else ["--aelita-host-key-sha256", parsed.aelita_host_key_sha256]
        ),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
