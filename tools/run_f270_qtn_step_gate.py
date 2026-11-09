#!/usr/bin/env python3
"""Run one F270 Quantenna same-value probe with UART and SSH evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/pydeps"))

import serial  # type: ignore  # vendored dependency


STEPS = (
    "rf-write-same",
    "interface-up-same",
    "mode-write-same",
    "ssid-write-same",
    "channel-write-same",
    "txpower-init-same",
    "txpower-limit-same",
    "doth-write-same",
    "tpc-write-same",
    "tpc-interval-same",
    "hostapd-restart-same",
    "post-rearm-same",
)
LOW_RISK = {"rf-write-same", "interface-up-same"}
REQUIRED_ACK = "OPENMITRASTAR_F270_QTN_STEP_PHYSICAL"
EXPECTED_VERSION = "lyoko-foundation-6.1.3-f270-qtn-step-path-fix-device"


def tcp_open(host: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=STEPS, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--allow-management-loss", action="store_true")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--known-hosts", type=Path, default=Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f270-device-bound/known_hosts.f270")
    args = parser.parse_args()

    preview = {
        "schema": "openmitrastar.f270-qtn-step-gate-plan/v1",
        "mode": "execute" if args.execute else "dry-run",
        "step": args.step,
        "risk": "low" if args.step in LOW_RISK else "management-loss-possible",
        "router": args.host,
        "uart": args.port,
        "flash": False,
        "writes_mtd": False,
    }
    print(json.dumps(preview, indent=2))
    if not args.execute:
        return 0
    if args.ack != REQUIRED_ACK:
        raise SystemExit("exact --ack is required")
    if args.step not in LOW_RISK and not args.allow_management_loss:
        raise SystemExit("--allow-management-loss is required for this step")
    if not tcp_open(args.host):
        raise SystemExit("router SSH is unavailable")
    if not args.known_hosts.is_file():
        raise SystemExit("pinned F270 known_hosts is unavailable")

    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    ssh_base = [
        ssh, "-i", str(Path.home() / ".ssh/id_ed25519"), "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=3",
        "-o", "ServerAliveCountMax=2", "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={args.known_hosts}", "-o", "LogLevel=ERROR", f"root@{args.host}",
    ]
    version = subprocess.run(
        [*ssh_base, "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    if version.returncode != 0 or version.stdout.strip() != EXPECTED_VERSION:
        raise SystemExit(f"expected F270 runtime, got {version.stdout.strip() or 'unavailable'}")

    out = (args.output_dir or ROOT / "outputs/postflash" / f"f270-qtn-step-{args.step}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}").resolve()
    out.mkdir(parents=True, exist_ok=True)
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
    command = f"OM_QTN_STEP_ACK=OPENMITRASTAR_QTN_STEP_V1 /usr/sbin/om-qtn-step probe {args.step}"
    try:
        proc = subprocess.run(
            [*ssh_base, command],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(exc.cmd, 124, exc.stdout or "", exc.stderr or "timeout")
    time.sleep(2)
    stop.set(); thread.join(timeout=2); uart.close()

    uart_text = b"".join(uart_chunks).decode("utf-8", errors="replace")
    uart_text = re.sub(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", "[mac-redacted]", uart_text)
    (out / "uart.log").write_text(uart_text, encoding="utf-8")
    (out / "ssh.stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (out / "ssh.stderr.log").write_text(proc.stderr or "", encoding="utf-8")

    ssh_after = tcp_open(args.host)
    marker_text = (proc.stdout or "") + "\n" + uart_text
    passed = proc.returncode == 0 and f"OMQTNSTEP pass step={args.step}" in marker_text and ssh_after
    result = {
        "schema": "openmitrastar.f270-qtn-step-gate/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "firmware": EXPECTED_VERSION,
        "step": args.step,
        "ssh_returncode": proc.returncode,
        "ssh_after": ssh_after,
        "begin_marker": f"OMQTNSTEP begin step={args.step}" in marker_text,
        "pass_marker": f"OMQTNSTEP pass step={args.step}" in marker_text,
        "fail_marker": f"OMQTNSTEP fail step={args.step}" in marker_text,
        "status": "PASS" if passed else "FAIL",
        "flash": False,
        "mtd_writes": False,
        "uart_log": str(out / "uart.log"),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
