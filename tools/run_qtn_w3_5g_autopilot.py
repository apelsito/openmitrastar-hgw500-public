#!/usr/bin/env python3
"""Cold-cycle-to-5GHz RAM-only autopilot for the MitraStar W3 ladder.

The orchestrator never flashes and never prints the PSK. It creates fresh,
preflighted cold-cycle runners, rearms a bounded number of waits, and only
advances when each child emits its exact PASS marker.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
import threading
import time

from run_qtn_w3_qcsapi_5g_ap import verify_psk


ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_W3_5G_AUTOPILOT_RAM_ONLY"
SWITCH_ACK = "OPENMITRASTAR_QTN_W3_SWITCH_EMAC_HANDOFF_RAM_ONLY"
SEQUENTIAL_ACK = "OPENMITRASTAR_QTN_W3_QDRV_SEQUENTIAL_RAM_ONLY"
AP_ACK = "OPENMITRASTAR_QTN_W3_QCSAPI_5G_AP36_BW80_RAM_ONLY"

SWITCH_PASS = "W3_SWITCH_EMAC_HANDOFF_EXPERIMENT_PASS=1"
SEQUENTIAL_PASS = "W3_QDRV_SEQUENTIAL_BRINGUP_EXPERIMENT_PASS=1"
AP_PASS = "W3_QCSAPI_5G_AP_EXPERIMENT_PASS=1"


def terminate_tree(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass


def redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text


def has_exact_marker(text: str, marker: str) -> bool:
    """Accept the marker only as a complete line or line-leading field."""
    return any(line == marker or line.startswith(marker + " ") for line in text.splitlines())


def preflight_children() -> bool:
    stages = (
        ([sys.executable, "tools/run_qtn_w3_switch_emac_handoff.py"],
         "W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1", "switch"),
        ([sys.executable, "tools/run_qtn_w3_qdrv_sequential_bringup.py"],
         "W3_QDRV_SEQUENTIAL_BRINGUP_DRY_RUN_PASS=1", "sequential"),
        ([sys.executable, "tools/run_qtn_w3_qcsapi_5g_ap.py"],
         "W3_QCSAPI_5G_AP_DRY_RUN_PASS=1", "ap"),
    )
    for command, marker, label in stages:
        result = subprocess.run(
            command, cwd=ROOT, text=True, capture_output=True,
            timeout=240, check=False,
        )
        if result.returncode != 0 or not has_exact_marker(result.stdout, marker):
            print(f"OM5GAUTO preflight={label} state=fail rc={result.returncode}", file=sys.stderr)
            return False
        print(f"OM5GAUTO preflight={label} state=pass", flush=True)
    return True


def _pipe_reader(stream: object, channel: str, queue: Queue[tuple[str, str | None]]) -> None:
    assert hasattr(stream, "readline")
    while True:
        chunk = stream.readline()
        if chunk == "":
            break
        queue.put((channel, chunk))
    queue.put((channel, None))


def run_stage(
    command: list[str], marker: str, label: str, timeout: float,
    *, ready_marker: str | None = None, secrets: tuple[str, ...] = (),
) -> bool:
    print(f"OM5GAUTO stage={label} state=start", flush=True)
    stamp = f"{label}-{time.time_ns()}"
    stage_root = ROOT / "outputs/runner-live/autopilot-stages"
    stage_root.mkdir(parents=True, exist_ok=True)
    stdout_path = stage_root / f"{stamp}.out.log"
    stderr_path = stage_root / f"{stamp}.err.log"
    output = ""
    ready_seen = ready_marker is None
    with stdout_path.open("w", encoding="utf-8", newline="") as stdout_handle, \
            stderr_path.open("w", encoding="utf-8", newline="") as stderr_handle:
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        assert process.stdout is not None and process.stderr is not None
        queue: Queue[tuple[str, str | None]] = Queue()
        threads = (
            threading.Thread(target=_pipe_reader, args=(process.stdout, "stdout", queue), daemon=True),
            threading.Thread(target=_pipe_reader, args=(process.stderr, "stderr", queue), daemon=True),
        )
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + timeout
        ended: set[str] = set()
        timed_out = False
        while len(ended) < 2:
            if process.poll() is None and time.monotonic() >= deadline:
                timed_out = True
                terminate_tree(process.pid)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        pass
            try:
                channel, chunk = queue.get(timeout=0.2)
            except Empty:
                if process.poll() is not None and all(not thread.is_alive() for thread in threads):
                    break
                continue
            if chunk is None:
                ended.add(channel)
                continue
            safe = redact(chunk, secrets)
            if channel == "stdout":
                output += chunk
                stdout_handle.write(safe)
                stdout_handle.flush()
                print(safe, end="", flush=True)
                if ready_marker and not ready_seen and ready_marker in output:
                    ready_seen = True
                    print(f"OM5GAUTO stage={label} state=armed", flush=True)
            else:
                stderr_handle.write(safe)
                stderr_handle.flush()
                print(safe, file=sys.stderr, end="", flush=True)
        for thread in threads:
            thread.join(timeout=2)
        if process.poll() is None and not timed_out:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                terminate_tree(process.pid)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        process.stdout.close()
        process.stderr.close()
        if timed_out:
            print(f"OM5GAUTO stage={label} state=timeout", file=sys.stderr, flush=True)
    passed = process.returncode == 0 and has_exact_marker(output, marker) and ready_seen
    print(
        f"OM5GAUTO stage={label} state={'pass' if passed else 'fail'} rc={process.returncode}",
        flush=True,
    )
    return passed


def switch_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "tools/run_qtn_w3_switch_emac_handoff.py",
        "--execute",
        "--ack",
        SWITCH_ACK,
        "--host",
        args.host,
        "--server-ip",
        args.server_ip,
        "--port",
        args.port,
        "--rollback-seconds",
        "75",
        "--timeout",
        str(args.cold_wait_seconds + 300),
        "--wait-for-cold-power-cycle",
        "--autoboot-wait-seconds",
        str(args.cold_wait_seconds),
    ]


def sequential_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "tools/run_qtn_w3_qdrv_sequential_bringup.py",
        "--execute",
        "--ack",
        SEQUENTIAL_ACK,
        "--host",
        args.host,
        "--port",
        args.port,
    ]


def ap_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "tools/run_qtn_w3_qcsapi_5g_ap.py",
        "--execute",
        "--ack",
        AP_ACK,
        "--psk-file",
        str(args.psk_file),
        "--host",
        args.host,
        "--port",
        args.port,
    ]


def dry_run() -> int:
    stages = (
        ([sys.executable, "tools/run_qtn_w3_switch_emac_handoff.py"],
         "W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1", "switch"),
        ([sys.executable, "tools/run_qtn_w3_qdrv_sequential_bringup.py"],
         "W3_QDRV_SEQUENTIAL_BRINGUP_DRY_RUN_PASS=1", "sequential"),
        ([sys.executable, "tools/run_qtn_w3_qcsapi_5g_ap.py"],
         "W3_QCSAPI_5G_AP_DRY_RUN_PASS=1", "ap"),
    )
    for command, marker, label in stages:
        if not run_stage(command, marker, f"dry-{label}", 180):
            return 1
    print("W3_QTN_5G_AUTOPILOT_DRY_RUN_PASS=1 flash=0 psk=not-read", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--psk-file", type=Path)
    parser.add_argument("--max-cold-attempts", type=int, default=3)
    parser.add_argument("--cold-wait-seconds", type=int, default=1800)
    args = parser.parse_args()

    if not args.execute:
        return dry_run()
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")
    if not 1 <= args.max_cold_attempts <= 5:
        raise SystemExit("--max-cold-attempts must be 1..5")
    if not 60 <= args.cold_wait_seconds <= 1800:
        raise SystemExit("--cold-wait-seconds must be 60..1800")
    if args.psk_file is None:
        raise SystemExit("--psk-file is required and must exist")
    args.psk_file = args.psk_file.resolve()
    verify_psk(args.psk_file)
    psk_secret = args.psk_file.read_text(encoding="ascii").splitlines()[0]
    if not preflight_children():
        raise SystemExit("child gate preflight failed before cold-cycle")

    print(
        "W3_QTN_5G_AUTOPILOT_START=1 mode=ram-only flash=0 "
        f"attempts={args.max_cold_attempts} psk=redacted",
        flush=True,
    )

    for attempt in range(1, args.max_cold_attempts + 1):
        print(f"OM5GAUTO stage=cold-cycle attempt={attempt} state=waiting-runner", flush=True)
        switch_passed = run_stage(
            switch_command(args), SWITCH_PASS, "switch",
            args.cold_wait_seconds + 900,
            ready_marker="RAMSSH_CYCLE_START",
            secrets=(psk_secret,),
        )
        if not switch_passed:
            print("OM5GAUTO action=await-next-physical-cold-cycle reason=switch", flush=True)
            continue

        if not run_stage(
            sequential_command(args), SEQUENTIAL_PASS, "sequential", 900,
            secrets=(psk_secret,),
        ):
            print("OM5GAUTO action=await-next-physical-cold-cycle reason=sequential", flush=True)
            continue

        if not run_stage(
            ap_command(args), AP_PASS, "ap36-bw80-es", 600,
            secrets=(psk_secret,),
        ):
            print("OM5GAUTO action=await-next-physical-cold-cycle reason=ap", flush=True)
            continue

        print(
            "W3_QTN_5G_AUTOPILOT_AP_CONTROL_PLANE_PASS=1 "
            "wifi0=ap channel=36 bw_mhz=80 region=ES flash=0 psk=redacted "
            "client_association=UNVERIFIED client_traffic=UNVERIFIED F3=0",
            flush=True,
        )
        return 0

    print("W3_QTN_5G_AUTOPILOT_EXPERIMENT_FAIL=1 reason=cold-attempts-exhausted", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
