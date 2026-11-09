#!/usr/bin/env python3
"""Run a strict, resumable sequential dual-radio soak on installed F301."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
from typing import Callable

import openmitrastar_f301_hardware_lock as hardware_lock


ROOT = Path(__file__).resolve().parents[1]
DEVICE = "hgw500bna-qcv2-a2-primary"
BUILD = Path.home() / f".openmitrastar/devices/{DEVICE}/firmware/f301-device-bound"
KNOWN_HOSTS = BUILD / "known_hosts.f301"
MANIFEST = BUILD / "manifest.json"
EXPECTED_VERSION = "lyoko-foundation-6.6.1-f301-f300-capability-truth-device"
EXPECTED_SHA256 = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
ACK = "OPENMITRASTAR_F301_SEQUENTIAL_DUAL_RADIO_SOAK"
RADIO5_ACK = "OPENMITRASTAR_F301_5G_AELITA_TRAFFIC"
PLAN_SCHEMA = "openmitrastar.f301-sequential-dual-radio-soak-plan/v1"
CHECKPOINT_SCHEMA = "openmitrastar.f301-sequential-dual-radio-soak-checkpoint/v1"
RESULT_SCHEMA = "openmitrastar.f301-sequential-dual-radio-soak/v1"
CYCLE_SCHEMA = "openmitrastar.f301-sequential-dual-radio-cycle/v1"
CYCLE_STATE_SCHEMA = "openmitrastar.f301-sequential-dual-radio-cycle-state/v1"
INVOCATION_SCHEMA = "openmitrastar.f301-sequential-dual-radio-soak-invocation/v1"
LOCK_OWNER = "f301-sequential-dual-radio-soak"
OUTPUT_PREFIX = "f301-sequential-dual-radio"
FIRMWARE_LABEL = "F301"
SNAPSHOT_ATTEMPTS = 5
SNAPSHOT_RETRY_SECONDS = 3.0


class CampaignFailure(RuntimeError):
    def __init__(self, phase: str, message: str) -> None:
        super().__init__(message)
        self.phase = phase


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    try:
        with temporary.open("w", encoding="ascii", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="ascii"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def tcp_open(host: str, port: int = 22, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def bounded_hours(value: str) -> float:
    parsed = float(value)
    if not 0.25 <= parsed <= 24:
        raise argparse.ArgumentTypeError("duration must be 0.25..24 hours")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def router_snapshot(host: str) -> dict[str, object]:
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    remote = r'''set -eu
printf 'FIRMWARE='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'MEMAVAILABLE_KB='; awk '/^MemAvailable:/ {print $2;exit}' /proc/meminfo
printf 'UPTIME='; cut -d' ' -f1 /proc/uptime
printf 'FATAL='; dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|qdrv.*fatal|muc.*fatal|auc.*fatal' || true
printf 'RADIO2='; /usr/sbin/om-radioctl status 2g
printf 'RADIO5='; /usr/sbin/om-radioctl status 5g
'''
    proc = subprocess.run(
        [
            ssh,
            "-i", str(Path.home() / ".ssh/id_ed25519"),
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            "-o", "LogLevel=ERROR",
            f"root@{host}", remote,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"router snapshot failed: {proc.stderr[:200].strip()}")
    result: dict[str, object] = {}
    for line in proc.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key in {"RADIO2", "RADIO5"}:
            result[key.lower()] = json.loads(value)
        elif key in {"MEMAVAILABLE_KB", "FATAL"}:
            result[key.lower()] = int(value or 0)
        elif key == "UPTIME":
            result["uptime_seconds"] = float(value or 0)
        elif key == "FIRMWARE":
            result["firmware"] = value
    required = {"firmware", "memavailable_kb", "uptime_seconds", "fatal", "radio2", "radio5"}
    missing = sorted(required.difference(result))
    if missing:
        raise RuntimeError(f"router snapshot missing fields: {', '.join(missing)}")
    return result


def router_snapshot_with_retry(
    host: str,
    attempts: int = SNAPSHOT_ATTEMPTS,
    delay_seconds: float = SNAPSHOT_RETRY_SECONDS,
    snapshot: Callable[[str], dict[str, object]] = router_snapshot,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    if attempts < 1:
        raise ValueError("snapshot attempts must be positive")
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            result = snapshot(host)
            result["snapshot_attempt"] = attempt
            return result
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                sleeper(delay_seconds)
    raise RuntimeError("router snapshot failed after retries: " + " | ".join(errors))


def run_logged(command: list[str], log: Path, timeout: int) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = proc.stdout or ""
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        output += f"\nTIMEOUT after {timeout} seconds\n"
        returncode = 124
    log.write_text(output, encoding="utf-8")
    return returncode


def latest_result(directory: Path, pattern: str) -> Path:
    files = list(directory.glob(pattern))
    if not files:
        raise RuntimeError(f"missing result in {directory}")
    return max(files, key=lambda path: path.stat().st_mtime_ns)


def mbps(item: dict[str, object]) -> float:
    return float(item.get("speed_Bps") or 0) * 8 / 1_000_000


def compact_cycle(
    index: int,
    radio2: dict[str, object],
    radio5: dict[str, object],
    router: dict[str, object],
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, object]:
    radio2_ok = bool(
        radio2.get("controller_download", {}).get("pass") is True
        and radio2.get("controller_upload", {}).get("pass") is True
        and radio2.get("router_health_gate", {}).get("pass") is True
        and radio2.get("execution_error") is None
    )
    radio5_ok = bool(
        radio5.get("status") == "PASS"
        and radio5.get("download", {}).get("pass") is True
        and radio5.get("upload", {}).get("pass") is True
        and int(radio5.get("soak", {}).get("disconnects") or 0) == 0
        and radio5.get("router", {}).get("status") == "PASS"
    )
    router_ok = bool(
        router.get("firmware") == EXPECTED_VERSION
        and int(router.get("fatal") or 0) == 0
        and int(router.get("memavailable_kb") or 0) >= 8192
        and router.get("radio2", {}).get("lifecycle") in {"ap-ready", "traffic-ready"}
        and router.get("radio5", {}).get("lifecycle") in {"ap-ready", "traffic-ready"}
    )
    return {
        "schema": CYCLE_SCHEMA,
        "cycle": index,
        "status": "PASS" if radio2_ok and radio5_ok and router_ok else "FAIL",
        "started_at": iso(started_at),
        "finished_at": iso(finished_at),
        "elapsed_seconds": round((finished_at - started_at).total_seconds(), 3),
        "radio2": {
            "download_mbps": round(mbps(radio2.get("controller_download", {})), 3),
            "upload_mbps": round(mbps(radio2.get("controller_upload", {})), 3),
            "router_health": radio2_ok,
            "rx_restarts": int(radio2.get("emac_stats_delta", {}).get("rx_restart_total") or 0),
        },
        "radio5": {
            "download_mbps": float(radio5.get("download", {}).get("mbps") or 0),
            "upload_mbps": float(radio5.get("upload", {}).get("mbps") or 0),
            "disconnects": int(radio5.get("soak", {}).get("disconnects") or 0),
        },
        "router": {
            "memavailable_kb": int(router.get("memavailable_kb") or 0),
            "uptime_seconds": float(router.get("uptime_seconds") or 0),
            "fatal": int(router.get("fatal") or 0),
            "snapshot_attempt": int(router.get("snapshot_attempt") or 1),
        },
    }


def summarize(
    cycles: list[dict[str, object]],
    started: datetime,
    updated: datetime,
    active_elapsed_seconds: float,
    target_duration_seconds: float,
    forced_status: str | None = None,
) -> dict[str, object]:
    all_passed = bool(cycles) and all(cycle.get("status") == "PASS" for cycle in cycles)
    duration_reached = active_elapsed_seconds >= target_duration_seconds
    if forced_status is not None:
        status = forced_status
    elif not all_passed:
        status = "FAIL"
    elif duration_reached:
        status = "PASS"
    else:
        status = "PAUSED"
    radio2_down = [float(cycle["radio2"]["download_mbps"]) for cycle in cycles]
    radio2_up = [float(cycle["radio2"]["upload_mbps"]) for cycle in cycles]
    radio5_down = [float(cycle["radio5"]["download_mbps"]) for cycle in cycles]
    radio5_up = [float(cycle["radio5"]["upload_mbps"]) for cycle in cycles]
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "started_at": iso(started),
        "updated_at": iso(updated),
        "active_elapsed_seconds": round(active_elapsed_seconds, 3),
        "target_duration_seconds": round(target_duration_seconds, 3),
        "duration_reached": duration_reached,
        "cycles_completed": len(cycles),
        "all_cycles_passed": all_passed,
        "median_mbps": {
            "radio2_down": round(statistics.median(radio2_down), 3) if radio2_down else 0,
            "radio2_up": round(statistics.median(radio2_up), 3) if radio2_up else 0,
            "radio5_down": round(statistics.median(radio5_down), 3) if radio5_down else 0,
            "radio5_up": round(statistics.median(radio5_up), 3) if radio5_up else 0,
        },
        "radio5_disconnects": sum(int(cycle["radio5"]["disconnects"]) for cycle in cycles),
        "rx_restarts": sum(int(cycle["radio2"]["rx_restarts"]) for cycle in cycles),
        "minimum_memavailable_kb": min(
            (int(cycle["router"]["memavailable_kb"]) for cycle in cycles), default=0
        ),
        "client_mode": "single-AELITA-sequential",
        "simultaneous_dual_radio": False,
        "flash": False,
        "mtd_writes": False,
    }


def load_completed_cycles(output_dir: Path) -> list[dict[str, object]]:
    directories = sorted(output_dir.glob("cycle-[0-9][0-9][0-9]"))
    cycles: list[dict[str, object]] = []
    for expected, directory in enumerate(directories, start=1):
        if directory.name != f"cycle-{expected:03d}":
            raise RuntimeError("soak cycle directories are not contiguous")
        result_path = directory / "cycle.json"
        if not result_path.is_file():
            raise RuntimeError(f"resume refused for incomplete cycle {expected}")
        result = read_json(result_path)
        if result.get("cycle") != expected or result.get("status") != "PASS":
            raise RuntimeError(f"resume refused for incomplete or failed cycle {expected}")
        cycles.append(result)
    return cycles


def checkpoint_started_at(checkpoint: dict[str, object]) -> datetime:
    started = datetime.fromisoformat(str(checkpoint.get("started_at") or ""))
    if started.tzinfo is None:
        raise RuntimeError("checkpoint started_at must include a timezone")
    return started


def immutable_plan(args: argparse.Namespace, candidate: Path, candidate_hash: str) -> dict[str, object]:
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
        "soak_seconds_per_band": args.soak_seconds,
        "cycle_pause_seconds": args.cycle_pause_seconds,
        "snapshot_attempts": args.snapshot_attempts,
        "snapshot_retry_seconds": args.snapshot_retry_seconds,
        "radio2_runner": "tools/run_aelita_2g_wpa2_speed_router_probe.py",
        "radio5_runner": "tools/run_f293_5g_aelita_traffic.py",
        "radio5_profile": "f301",
        "radio5_ack": RADIO5_ACK,
        "client_mode": "single-AELITA-sequential",
        "simultaneous_dual_radio": False,
        "restore_ssid": "MOVISTAR-WIFI6-A348",
        "hardware_preflight": "DEFERRED_TO_EXECUTE" if not args.execute else "REQUIRED",
        "hardware_actions_performed": False,
        "flash": False,
        "mtd_writes": False,
    }


def validate_resume(
    output_dir: Path,
    expected_plan: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]], datetime, float]:
    plan_path = output_dir / "plan.json"
    checkpoint_path = output_dir / "checkpoint.json"
    if not plan_path.is_file() or not checkpoint_path.is_file():
        raise RuntimeError("resume requires plan.json and checkpoint.json")
    previous = read_json(plan_path)
    stable_keys = (
        "schema", "mode", "required_firmware", "candidate_file", "candidate_sha256",
        "known_hosts_file", "router_host", "oracle_host", "oracle_user", "controller_url",
        "duration_hours", "target_duration_seconds", "soak_seconds_per_band",
        "cycle_pause_seconds", "snapshot_attempts", "snapshot_retry_seconds",
        "radio2_runner", "radio5_runner", "radio5_profile", "radio5_ack", "restore_ssid",
    )
    mismatches = [key for key in stable_keys if previous.get(key) != expected_plan.get(key)]
    if mismatches:
        raise RuntimeError("resume plan mismatch: " + ", ".join(mismatches))
    if previous.get("mode") != "execute":
        raise RuntimeError("resume requires an execute-mode plan")
    checkpoint = read_json(checkpoint_path)
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        raise RuntimeError("resume checkpoint schema mismatch")
    if checkpoint.get("status") not in {"PAUSED", "IN_PROGRESS"}:
        raise RuntimeError(f"resume refused for terminal checkpoint {checkpoint.get('status')!r}")
    if (output_dir / "result.json").exists() or (output_dir / "failure.json").exists():
        raise RuntimeError("resume refused because terminal evidence exists")
    cycles = load_completed_cycles(output_dir)
    if int(checkpoint.get("cycles_completed") or 0) != len(cycles):
        raise RuntimeError("resume checkpoint cycle count mismatch")
    active_elapsed = float(checkpoint.get("active_elapsed_seconds") or 0)
    target = float(expected_plan["target_duration_seconds"])
    if active_elapsed < 0 or active_elapsed >= target:
        raise RuntimeError("resume checkpoint active duration is inconsistent")
    return checkpoint, cycles, checkpoint_started_at(checkpoint), active_elapsed


def radio2_command(args: argparse.Namespace, output_dir: Path) -> list[str]:
    return [
        sys.executable, str(ROOT / "tools/run_aelita_2g_wpa2_speed_router_probe.py"),
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
        sys.executable, str(ROOT / "tools/run_f293_5g_aelita_traffic.py"),
        "--profile", "f301",
        "--execute", "--ack", RADIO5_ACK,
        "--router-host", args.router_host,
        "--oracle-host", args.oracle_host,
        "--oracle-user", args.oracle_user,
        "--controller-url", args.controller_url,
        "--soak-seconds", str(args.soak_seconds),
        "--output-dir", str(output_dir),
    ]


def checkpoint_payload(
    cycles: list[dict[str, object]],
    started: datetime,
    active_elapsed: float,
    target_seconds: float,
    status: str,
) -> dict[str, object]:
    payload = summarize(cycles, started, utcnow(), active_elapsed, target_seconds, status)
    payload["schema"] = CHECKPOINT_SCHEMA
    payload["next_cycle"] = len(cycles) + 1
    return payload


def failure_payload(
    exc: Exception,
    phase: str,
    cycle_index: int | None,
    cycles: list[dict[str, object]],
    started: datetime,
    active_elapsed: float,
    target_seconds: float,
) -> dict[str, object]:
    payload = summarize(cycles, started, utcnow(), active_elapsed, target_seconds, "FAIL")
    payload.update(
        {
            "failure_phase": phase,
            "failure_cycle": cycle_index,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "evidence_preserved": True,
        }
    )
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--ack", default="")
    result.add_argument("--router-host", default="192.168.1.90")
    result.add_argument("--oracle-host", default="192.168.1.63")
    result.add_argument("--oracle-user", default="AELITA")
    result.add_argument("--controller-url", default="http://192.168.1.43:8008/speed.bin")
    result.add_argument("--duration-hours", type=bounded_hours, default=6.0)
    result.add_argument("--soak-seconds", type=int, default=120)
    result.add_argument("--cycle-pause-seconds", type=nonnegative_int, default=30)
    result.add_argument("--max-cycles", type=nonnegative_int, default=0,
                        help="maximum cycles in this invocation; 0 means unlimited")
    result.add_argument("--snapshot-attempts", type=int, default=SNAPSHOT_ATTEMPTS)
    result.add_argument("--snapshot-retry-seconds", type=float, default=SNAPSHOT_RETRY_SECONDS)
    result.add_argument("--resume", action="store_true")
    result.add_argument("--output-dir", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 120 <= args.soak_seconds <= 600:
        raise SystemExit("--soak-seconds must be 120..600")
    if args.snapshot_attempts < 1 or not 0 <= args.snapshot_retry_seconds <= 60:
        raise SystemExit("snapshot retry must use at least one attempt and a 0..60 second delay")
    if not MANIFEST.is_file():
        raise SystemExit(f"missing F301 manifest: {MANIFEST}")
    manifest = read_json(MANIFEST)
    artifact = manifest.get("artifacts", {}).get("webformat", {})
    candidate = BUILD / str(artifact.get("file") or "")
    if not candidate.is_file():
        raise SystemExit(f"missing F301 candidate: {candidate}")
    candidate_hash = sha256(candidate)
    if args.output_dir is None:
        stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
        args.output_dir = ROOT / f"outputs/soak/{OUTPUT_PREFIX}-{stamp}"
    args.output_dir = args.output_dir.resolve()
    plan = immutable_plan(args, candidate, candidate_hash)
    local_ready = bool(
        candidate_hash == EXPECTED_SHA256
        and artifact.get("sha256") == EXPECTED_SHA256
        and KNOWN_HOSTS.is_file()
    )
    plan["local_preflight_pass"] = local_ready

    if args.resume:
        if not args.execute:
            raise SystemExit("--resume requires --execute")
        if not args.output_dir.is_dir():
            raise SystemExit("--resume requires an existing output directory")
        try:
            _, completed_cycles, started, prior_active = validate_resume(args.output_dir, plan)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise SystemExit("refusing to overwrite existing soak evidence; use --resume")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.output_dir / "plan.json", plan)
        completed_cycles = []
        started = utcnow()
        prior_active = 0.0

    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.execute:
        return 0 if local_ready else 1
    if args.ack != ACK:
        raise SystemExit("exact --ack is required")
    if not local_ready:
        raise SystemExit("F301 local artifact preflight failed")
    target_seconds = args.duration_hours * 3600
    session_started_monotonic = time.monotonic()

    def active_elapsed() -> float:
        return prior_active + max(0.0, time.monotonic() - session_started_monotonic)

    cycles = list(completed_cycles)
    checkpoint_path = args.output_dir / "checkpoint.json"
    invocation_number = len(list(args.output_dir.glob("invocation-*.json"))) + 1
    invocation_path = args.output_dir / f"invocation-{invocation_number:03d}.json"
    atomic_write_json(
        invocation_path,
        {
            "schema": INVOCATION_SCHEMA,
            "invocation": invocation_number,
            "resume": args.resume,
            "started_at": iso(utcnow()),
            "max_cycles": args.max_cycles,
            "cycles_already_completed": len(cycles),
            "prior_active_elapsed_seconds": round(prior_active, 3),
        },
    )
    atomic_write_json(
        checkpoint_path,
        checkpoint_payload(cycles, started, active_elapsed(), target_seconds, "IN_PROGRESS"),
    )

    server = ROOT / "tools/ensure_lyoko_speed_server.ps1"
    server_started = False
    phase = "physical-lock"
    current_cycle: int | None = None
    physical_lock = hardware_lock.acquire_physical_lock(
        LOCK_OWNER, args.output_dir
    )
    try:
        physical_lock.acquire()
        phase = "ssh-preflight"
        if not tcp_open(args.router_host) or not tcp_open(args.oracle_host):
            raise CampaignFailure(phase, f"{FIRMWARE_LABEL} soak SSH preflight failed")
        phase = "initial-snapshot"
        before = router_snapshot_with_retry(
            args.router_host, args.snapshot_attempts, args.snapshot_retry_seconds
        )
        if before.get("firmware") != EXPECTED_VERSION:
            raise CampaignFailure(
                "initial-snapshot",
                f"expected {FIRMWARE_LABEL} runtime, got {before.get('firmware')!r}",
            )
        phase = "speed-server-start"
        server_proc = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(server),
                "-Action", "Ensure", "-Port", "8008", "-PayloadMiB", "32",
                "-AllowedClient", args.oracle_host,
            ],
            cwd=ROOT,
            check=False,
        )
        if server_proc.returncode:
            raise CampaignFailure(phase, f"speed server start failed with rc={server_proc.returncode}")
        server_started = True

        cycles_this_invocation = 0
        while active_elapsed() < target_seconds:
            if args.max_cycles and cycles_this_invocation >= args.max_cycles:
                break
            index = len(cycles) + 1
            current_cycle = index
            cycle_started = utcnow()
            cycle_dir = args.output_dir / f"cycle-{index:03d}"
            if cycle_dir.exists():
                raise CampaignFailure("cycle-prepare", f"cycle evidence already exists: {cycle_dir}")
            radio2_dir = cycle_dir / "radio2"
            radio5_dir = cycle_dir / "radio5"
            cycle_dir.mkdir(parents=True)
            atomic_write_json(
                cycle_dir / "state.json",
                {
                    "schema": CYCLE_STATE_SCHEMA,
                    "cycle": index,
                    "status": "IN_PROGRESS",
                    "phase": "radio2",
                    "started_at": iso(cycle_started),
                },
            )
            phase = "radio2"
            rc2 = run_logged(
                radio2_command(args, radio2_dir),
                cycle_dir / "radio2.log",
                args.soak_seconds + 900,
            )
            if rc2:
                raise CampaignFailure(phase, f"cycle {index} 2.4 GHz failed with rc={rc2}")
            radio2_summary = radio2_dir / "summary.json"
            if not radio2_summary.is_file():
                raise CampaignFailure(phase, f"cycle {index} 2.4 GHz summary is missing")
            radio2 = json.loads(radio2_summary.read_text(encoding="utf-8"))

            phase = "radio5"
            state = read_json(cycle_dir / "state.json")
            state["phase"] = phase
            atomic_write_json(cycle_dir / "state.json", state)
            rc5 = run_logged(
                radio5_command(args, radio5_dir),
                cycle_dir / "radio5.log",
                args.soak_seconds + 900,
            )
            if rc5:
                raise CampaignFailure(phase, f"cycle {index} 5 GHz failed with rc={rc5}")
            radio5 = json.loads(latest_result(radio5_dir, "result-*.json").read_text(encoding="utf-8"))

            phase = "router-snapshot"
            state["phase"] = phase
            atomic_write_json(cycle_dir / "state.json", state)
            router = router_snapshot_with_retry(
                args.router_host, args.snapshot_attempts, args.snapshot_retry_seconds
            )
            cycle = compact_cycle(index, radio2, radio5, router, cycle_started, utcnow())
            atomic_write_json(cycle_dir / "cycle.json", cycle)
            state.update({"status": cycle["status"], "phase": "complete", "finished_at": cycle["finished_at"]})
            atomic_write_json(cycle_dir / "state.json", state)
            if cycle["status"] != "PASS":
                raise CampaignFailure("cycle-health", f"cycle {index} health gate failed")
            cycles.append(cycle)
            cycles_this_invocation += 1
            current_cycle = None
            atomic_write_json(
                checkpoint_path,
                checkpoint_payload(cycles, started, active_elapsed(), target_seconds, "IN_PROGRESS"),
            )
            if active_elapsed() >= target_seconds:
                break
            if args.max_cycles and cycles_this_invocation >= args.max_cycles:
                break
            remaining = max(0.0, target_seconds - active_elapsed())
            if remaining:
                time.sleep(min(float(args.cycle_pause_seconds), remaining))

        elapsed = active_elapsed()
        if elapsed >= target_seconds and cycles:
            phase = "final-snapshot"
            final_snapshot = router_snapshot_with_retry(
                args.router_host, args.snapshot_attempts, args.snapshot_retry_seconds
            )
            final_router_ok = bool(
                final_snapshot.get("firmware") == EXPECTED_VERSION
                and int(final_snapshot.get("fatal") or 0) == 0
                and int(final_snapshot.get("memavailable_kb") or 0) >= 8192
                and final_snapshot.get("radio2", {}).get("lifecycle") in {"ap-ready", "traffic-ready"}
                and final_snapshot.get("radio5", {}).get("lifecycle") in {"ap-ready", "traffic-ready"}
            )
            if not final_router_ok:
                raise CampaignFailure(phase, "final router health gate failed")
            result = summarize(cycles, started, utcnow(), elapsed, target_seconds)
            result["final_router"] = final_snapshot
            atomic_write_json(args.output_dir / "result.json", result)
            atomic_write_json(
                checkpoint_path,
                checkpoint_payload(cycles, started, elapsed, target_seconds, "PASS"),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        paused = summarize(cycles, started, utcnow(), elapsed, target_seconds, "PAUSED")
        paused["pause_reason"] = "max-cycles" if args.max_cycles else "duration-not-reached"
        paused["resumable"] = True
        atomic_write_json(
            checkpoint_path,
            checkpoint_payload(cycles, started, elapsed, target_seconds, "PAUSED"),
        )
        pause_path = args.output_dir / f"pause-{invocation_number:03d}.json"
        atomic_write_json(pause_path, paused)
        print(json.dumps(paused, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        effective_phase = exc.phase if isinstance(exc, CampaignFailure) else phase
        failure = failure_payload(
            exc, effective_phase, current_cycle, cycles, started, active_elapsed(), target_seconds
        )
        if current_cycle is not None:
            cycle_dir = args.output_dir / f"cycle-{current_cycle:03d}"
            atomic_write_json(cycle_dir / "failure.json", failure)
            atomic_write_json(
                cycle_dir / "state.json",
                {
                    "schema": CYCLE_STATE_SCHEMA,
                    "cycle": current_cycle,
                    "status": "FAIL",
                    "phase": effective_phase,
                    "finished_at": iso(utcnow()),
                    "error": str(exc)[:1000],
                },
            )
        atomic_write_json(args.output_dir / "failure.json", failure)
        atomic_write_json(args.output_dir / "result.json", failure)
        atomic_write_json(
            checkpoint_path,
            checkpoint_payload(cycles, started, active_elapsed(), target_seconds, "FAIL"),
        )
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if server_started:
            subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(server),
                    "-Action", "Stop", "-Port", "8008", "-AllowedClient", args.oracle_host,
                ],
                cwd=ROOT,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if physical_lock.acquired:
            physical_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
