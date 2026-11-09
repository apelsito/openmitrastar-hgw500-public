#!/usr/bin/env python3
"""Measure bidirectional management transport without writing persistent data."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import paramiko  # noqa: E402
from ramssh_exec import load_private_key  # noqa: E402


def mbps(byte_count: int, seconds: float) -> float:
    return round(byte_count * 8 / max(seconds, 0.001) / 1_000_000, 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1024 * 1024 <= args.bytes <= 64 * 1024 * 1024:
        raise SystemExit("--bytes must be 1..64 MiB")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host, username="root", pkey=load_private_key(),
        look_for_keys=False, allow_agent=False, timeout=5,
        banner_timeout=8, auth_timeout=8,
    )
    try:
        count = args.bytes // 65536
        start = time.monotonic()
        _, stdout, stderr = client.exec_command(
            f"dd if=/dev/zero bs=65536 count={count} 2>/dev/null", timeout=120
        )
        received = 0
        while True:
            chunk = stdout.channel.recv(65536)
            if not chunk:
                break
            received += len(chunk)
        download_seconds = time.monotonic() - start
        download_rc = stdout.channel.recv_exit_status()
        download_err = stderr.read().decode("utf-8", "replace").strip()

        stdin, stdout, stderr = client.exec_command("dd of=/dev/null bs=65536 2>/dev/null", timeout=120)
        payload = b"\0" * 65536
        sent = 0
        start = time.monotonic()
        while sent < args.bytes:
            size = min(len(payload), args.bytes - sent)
            stdin.channel.sendall(payload[:size])
            sent += size
        stdin.channel.shutdown_write()
        upload_rc = stdout.channel.recv_exit_status()
        upload_seconds = time.monotonic() - start
        upload_err = stderr.read().decode("utf-8", "replace").strip()
    finally:
        client.close()

    result = {
        "schema": "openmitrastar.ramssh-transport/v1",
        "host": args.host,
        "bytes_requested": args.bytes,
        "router_to_pc": {
            "bytes": received,
            "seconds": round(download_seconds, 3),
            "mbps": mbps(received, download_seconds),
            "rc": download_rc,
            "stderr": download_err or None,
        },
        "pc_to_router": {
            "bytes": sent,
            "seconds": round(upload_seconds, 3),
            "mbps": mbps(sent, upload_seconds),
            "rc": upload_rc,
            "stderr": upload_err or None,
        },
        "persistent_writes": False,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if received == args.bytes and download_rc == 0 and upload_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
