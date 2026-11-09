#!/usr/bin/env python3
"""Run the F285 fixed 5 GHz SSID material trial with UART and rollback evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "work/pydeps"))

import serial  # type: ignore
from run_f282_qtn_step_gate import snapshot, ssh_command, state_preserved, tcp_open


EXPECTED_VERSION = "lyoko-foundation-6.3.9-f285-qtn-convergent-verify-device"
REQUIRED_ACK = "OPENMITRASTAR_F285_QTN_MATERIAL_PHYSICAL"
TRIAL_ACK = "OPENMITRASTAR_QTN_MATERIAL_TRIAL_V1"
KNOWN_HOSTS = (
    Path.home()
    / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f285-device-bound/known_hosts.f285"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--physical-recovery-ready", action="store_true")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--hold-seconds", type=int, default=15)
    parser.add_argument("--watchdog-seconds", type=int, default=60)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not 5 <= args.hold_seconds <= 30:
        raise SystemExit("--hold-seconds must be 5..30")
    if not 30 <= args.watchdog_seconds <= 180 or args.watchdog_seconds <= args.hold_seconds:
        raise SystemExit("--watchdog-seconds must be 30..180 and exceed hold time")

    preview = {
        "schema": "openmitrastar.f285-qtn-material-gate-plan/v1",
        "mode": "execute" if args.execute else "dry-run",
        "firmware": EXPECTED_VERSION,
        "target_ssid": "Lyoko-5G-Material-Test",
        "change": {"ssid": True, "channel": False, "bandwidth": False, "psk": False},
        "hold_seconds": args.hold_seconds,
        "watchdog_seconds": args.watchdog_seconds,
        "flash": False,
        "mtd_writes": False,
    }
    print(json.dumps(preview, indent=2))
    if not args.execute:
        return 0
    if args.ack != REQUIRED_ACK:
        raise SystemExit("exact --ack is required")
    if not args.physical_recovery_ready:
        raise SystemExit("--physical-recovery-ready is required")
    if not KNOWN_HOSTS.is_file() or not tcp_open(args.host):
        raise SystemExit("F285 pinned SSH preflight failed")

    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    ssh_base = [
        ssh, "-i", str(Path.home() / ".ssh/id_ed25519"),
        "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=3",
        "-o", "ServerAliveCountMax=2", "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "LogLevel=ERROR",
        f"root@{args.host}",
    ]
    version = ssh_command(
        ssh_base,
        "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release",
        timeout=15,
    )
    if version.returncode != 0 or version.stdout.strip() != EXPECTED_VERSION:
        raise SystemExit(f"expected F285 runtime, got {version.stdout.strip() or 'unavailable'}")
    before, before_proc = snapshot(ssh_base)
    if before is None:
        raise SystemExit(f"pre-trial snapshot failed: {before_proc.stderr.strip() or 'invalid output'}")

    out = (
        args.output_dir
        or ROOT / "outputs/postflash" / f"f285-qtn-material-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    ).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "before.json").write_text(json.dumps(before, indent=2) + "\n", encoding="ascii")

    stop = threading.Event()
    uart_chunks: list[bytes] = []
    uart = serial.Serial(args.port, 115200, timeout=0.1, write_timeout=2)

    def reader() -> None:
        while not stop.is_set():
            data = uart.read(4096)
            if data:
                uart_chunks.append(data)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    command = (
        f"OM_QTN_TRIAL_ACK={TRIAL_ACK} "
        f"OM_QTN_TRIAL_HOLD_SECONDS={args.hold_seconds} "
        f"OM_QTN_TRIAL_WATCHDOG_SECONDS={args.watchdog_seconds} "
        "/usr/sbin/om-qtn-material-trial run"
    )
    try:
        proc = ssh_command(ssh_base, command, timeout=args.watchdog_seconds + 30)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(exc.cmd, 124, exc.stdout or "", exc.stderr or "timeout")
    time.sleep(2)
    stop.set()
    thread.join(timeout=2)
    uart.close()

    uart_text = b"".join(uart_chunks).decode("utf-8", errors="replace")
    uart_text = re.sub(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", "[mac-redacted]", uart_text)
    (out / "uart.log").write_text(uart_text, encoding="utf-8")
    (out / "ssh.stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (out / "ssh.stderr.log").write_text(proc.stderr or "", encoding="utf-8")

    after = None
    samples: list[dict[str, object]] = []
    deadline = time.monotonic() + args.watchdog_seconds + 10
    while time.monotonic() < deadline:
        if tcp_open(args.host):
            candidate, _ = snapshot(ssh_base)
            if candidate is not None:
                after = candidate
                preserved = state_preserved(before, candidate)
                samples.append({"elapsed_seconds": round(time.monotonic() - (deadline - args.watchdog_seconds - 10), 3), "state_preserved": preserved, "snapshot": candidate})
                if preserved:
                    break
        time.sleep(2)
    (out / "after-samples.json").write_text(json.dumps(samples, indent=2) + "\n", encoding="ascii")
    if after is not None:
        (out / "after.json").write_text(json.dumps(after, indent=2) + "\n", encoding="ascii")

    text = (proc.stdout or "") + "\n" + uart_text
    restored = state_preserved(before, after)
    passed = bool(
        proc.returncode == 0
        and "OMQTNTRIAL stage=target-apply-pass" in text
        and "OMQTNTRIAL stage=restore-pass" in text
        and restored
        and tcp_open(args.host)
    )
    result = {
        "schema": "openmitrastar.f285-qtn-material-gate/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "firmware": EXPECTED_VERSION,
        "target_ssid": "Lyoko-5G-Material-Test",
        "ssh_returncode": proc.returncode,
        "target_marker": "OMQTNTRIAL stage=target-apply-pass" in text,
        "restore_marker": "OMQTNTRIAL stage=restore-pass" in text,
        "state_restored": restored,
        "ssh_after": tcp_open(args.host),
        "fatal_count_before": before["fatal_count"],
        "fatal_count_after": None if after is None else after["fatal_count"],
        "status": "PASS" if passed else "FAIL",
        "flash": False,
        "mtd_writes": False,
        "automatic_retry": False,
        "watchdog_present": True,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
