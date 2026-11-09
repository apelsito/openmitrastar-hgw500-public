#!/usr/bin/env python3
"""Autonomous observe-only client/traffic gate for the 2.4 GHz lab.

The loop waits for a genuinely authorized station, starts bounded packet
captures on wlan0/eth0, runs the existing traffic monitor, evaluates the
result, stores every artifact, and then waits for the next cycle.  It never
reloads modules, changes radio state, touches boot variables, MTD, or flash.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def run(argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )


def remote(host: str, command: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return run(
        [
            sys.executable,
            str(TOOLS / "ramssh_exec.py"),
            "--host",
            host,
            "--timeout",
            str(timeout),
            command,
        ],
        capture=True,
    )


def fetch_remote(host: str, remote_path: str, local_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(TOOLS / "ramssh_exec.py"),
            "--host",
            host,
            "--timeout",
            "30",
            f"cat {remote_path}",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    local_path.write_bytes(proc.stdout)
    if proc.returncode != 0:
        local_path.with_suffix(local_path.suffix + ".error.txt").write_bytes(proc.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--wait-seconds", type=int, default=7200)
    parser.add_argument("--capture-seconds", type=int, default=120)
    parser.add_argument("--cycles", type=int, default=0, help="0 means continuous")
    parser.add_argument("--cooldown", type=int, default=15)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/kernel-port/realtek-loop/auto-live",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.wait_seconds < 1 or not 10 <= args.capture_seconds <= 1800:
        raise SystemExit("invalid wait/capture duration")
    if args.cycles < 0 or args.cooldown < 0:
        raise SystemExit("cycles/cooldown must be non-negative")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema": "openmitrastar.auto-2g-live-lab/v1",
        "host": args.host,
        "wait_seconds": args.wait_seconds,
        "capture_seconds": args.capture_seconds,
        "cycles": args.cycles,
        "cooldown": args.cooldown,
        "mutations": False,
        "flash": False,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        print("OM2G_AUTO_DRY_RUN_PASS=1")
        return 0

    lock = args.output_dir / "auto-2g-live.pid"
    if lock.exists():
        try:
            old_pid = int(lock.read_text(encoding="ascii").strip())
            os.kill(old_pid, 0)
        except (OSError, ValueError):
            lock.unlink(missing_ok=True)
        else:
            raise SystemExit(f"auto monitor already running as PID {old_pid}")
    lock.write_text(f"{os.getpid()}\n", encoding="ascii")

    completed = 0
    try:
        print("OM2G_AUTO_BEGIN=1", flush=True)
        while args.cycles == 0 or completed < args.cycles:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            wait_json = args.output_dir / f"{stamp}-client.json"
            wait_proc = run(
                [
                    sys.executable,
                    str(TOOLS / "wait_w2_2g_client.py"),
                    "--host",
                    args.host,
                    "--wait-seconds",
                    str(args.wait_seconds),
                    "--interval",
                    "1",
                    "--require-authorized",
                    "--output",
                    str(wait_json),
                ]
            )
            if wait_proc.returncode != 0:
                print("OM2G_AUTO_WAIT_RETRY=1", flush=True)
                time.sleep(args.cooldown)
                continue

            remote_tag = f"om-auto-{stamp}"
            remote_wlan = f"/tmp/{remote_tag}-wlan.log"
            remote_eth = f"/tmp/{remote_tag}-eth.log"
            arm = remote(
                args.host,
                "set +e; "
                f"rm -f {remote_wlan} {remote_eth}; "
                f"/tmp/om-packet-trace wlan0 {args.capture_seconds} </dev/null >{remote_wlan} 2>&1 & "
                f"/tmp/om-packet-trace eth0 {args.capture_seconds} </dev/null >{remote_eth} 2>&1 & "
                "echo OM2G_AUTO_PACKET_CAPTURE_ARMED=1",
            )
            if arm.returncode != 0:
                print(f"OM2G_AUTO_PACKET_CAPTURE_ERROR={arm.stderr.strip()[:200]}", flush=True)

            raw_log = args.output_dir / f"{stamp}-traffic.raw.log"
            monitor_stdout = args.output_dir / f"{stamp}-monitor.stdout.log"
            monitor_stderr = args.output_dir / f"{stamp}-monitor.stderr.log"
            monitor_proc = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "monitor_2g_live_traffic.py"),
                    "--host",
                    args.host,
                    "--seconds",
                    str(args.capture_seconds),
                    "--interval",
                    "1",
                    "--pre-seconds",
                    "5",
                    "--post-seconds",
                    "5",
                    "--output",
                    str(raw_log),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            monitor_stdout.write_text(monitor_proc.stdout, encoding="utf-8")
            monitor_stderr.write_text(monitor_proc.stderr, encoding="utf-8")

            summary = raw_log.with_suffix(raw_log.suffix + ".json")
            evaluation = args.output_dir / f"{stamp}-evaluation.json"
            if summary.is_file():
                run(
                    [
                        sys.executable,
                        str(TOOLS / "evaluate_w2_2g_live_traffic.py"),
                        str(summary),
                        "--output",
                        str(evaluation),
                    ]
                )

            fetch_remote(args.host, remote_wlan, args.output_dir / f"{stamp}-packet-wlan0.log")
            fetch_remote(args.host, remote_eth, args.output_dir / f"{stamp}-packet-eth0.log")
            completed += 1
            print(
                f"OM2G_AUTO_CYCLE_COMPLETE={completed} summary={summary} evaluation={evaluation}",
                flush=True,
            )
            time.sleep(args.cooldown)
    finally:
        lock.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
