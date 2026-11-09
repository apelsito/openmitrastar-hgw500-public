#!/usr/bin/env python3
"""Authenticate to the RAM-only OpenMitraStar Dropbear without exposing keys."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko  # noqa: E402


def load_private_key() -> paramiko.Ed25519Key:
    key = subprocess.check_output(
        [
            "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e",
            "cat", "/home/user/openmitrastar-ramssh-keys/client_ed25519",
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return paramiko.Ed25519Key.from_private_key(io.StringIO(key))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    key = load_private_key()
    deadline = time.monotonic() + args.timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                args.host,
                port=args.port,
                username="root",
                pkey=key,
                look_for_keys=False,
                allow_agent=False,
                timeout=3,
                banner_timeout=5,
                auth_timeout=5,
            )
            _, stdout, stderr = client.exec_command(
                "echo RAMSSH_AUTH_OK; uname -a; cat /proc/version",
                timeout=15,
            )
            output = stdout.read().decode("utf-8", "replace")
            errors = stderr.read().decode("utf-8", "replace")
            if "RAMSSH_AUTH_OK" not in output:
                raise RuntimeError(f"authenticated command marker missing: {errors}")
            print(output.strip())
            print("RAMSSH_AUTHENTICATED_GATE_PASS=1")
            return 0
        except Exception as exc:  # target may still be bringing the link up
            last_error = exc
            time.sleep(1)
        finally:
            client.close()
    print(f"RAMSSH_AUTHENTICATED_GATE_FAIL: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
