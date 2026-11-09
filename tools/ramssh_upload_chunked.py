#!/usr/bin/env python3
"""Upload a large file over bounded Dropbear exec channels with hash readback."""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path
import shlex
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko  # noqa: E402


def load_private_key() -> paramiko.Ed25519Key:
    key = subprocess.check_output(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e",
         "cat", "/home/user/openmitrastar-ramssh-keys/client_ed25519"],
        text=True, stderr=subprocess.DEVNULL,
    )
    return paramiko.Ed25519Key.from_private_key(io.StringIO(key))


def connect(host: str, key: paramiko.Ed25519Key) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username="root", pkey=key, look_for_keys=False,
                   allow_agent=False, timeout=5, banner_timeout=8, auth_timeout=8)
    return client


def exec_small(host: str, key: paramiko.Ed25519Key, command: str) -> tuple[int, bytes, bytes]:
    client = connect(host, key)
    try:
        _, stdout, stderr = client.exec_command(command, timeout=30)
        out, err = stdout.read(), stderr.read()
        return stdout.channel.recv_exit_status(), out, err
    finally:
        client.close()


def send_chunk(host: str, key: paramiko.Ed25519Key, destination: str, chunk: bytes) -> None:
    client = connect(host, key)
    try:
        stdin, stdout, stderr = client.exec_command(f"cat >> {destination}", timeout=30)
        stdin.channel.sendall(chunk)
        stdin.channel.shutdown_write()
        out, err = stdout.read(), stderr.read()
        status = stdout.channel.recv_exit_status()
        if status:
            raise RuntimeError(f"remote append rc={status} out={out!r} err={err!r}")
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--mode", default="0700")
    parser.add_argument("--chunk-bytes", type=int, default=65536)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    if not 16384 <= args.chunk_bytes <= 131072:
        raise SystemExit("--chunk-bytes must be 16384..131072")
    if not 1 <= args.retries <= 5:
        raise SystemExit("--retries must be 1..5")
    payload = args.source.read_bytes()
    expected = hashlib.sha256(payload).hexdigest()
    destination = shlex.quote(args.destination)
    temporary = shlex.quote(args.destination + ".part")
    mode = shlex.quote(args.mode)
    key = load_private_key()

    status, _, err = exec_small(args.host, key, f"rm -f {temporary}; : > {temporary}; chmod 0600 {temporary}")
    if status:
        raise RuntimeError(f"remote initialize failed rc={status} err={err!r}")
    total = (len(payload) + args.chunk_bytes - 1) // args.chunk_bytes
    for index, start in enumerate(range(0, len(payload), args.chunk_bytes), 1):
        chunk = payload[start:start + args.chunk_bytes]
        for attempt in range(1, args.retries + 1):
            try:
                send_chunk(args.host, key, temporary, chunk)
                break
            except Exception:
                if attempt == args.retries:
                    raise
                time.sleep(attempt)
        print(f"RAMSSH_CHUNK_OK index={index}/{total} bytes={len(chunk)}", flush=True)

    command = (
        f"actual=$(/bin/busybox sha256sum {temporary} | awk '{{print $1}}'); "
        f"test \"$actual\" = {expected}; mv {temporary} {destination}; "
        f"chmod {mode} {destination}; echo RAMSSH_CHUNKED_REMOTE_SHA256=$actual"
    )
    status, out, err = exec_small(args.host, key, command)
    if out:
        sys.stdout.buffer.write(out)
    if err:
        sys.stderr.buffer.write(err)
    if status:
        raise RuntimeError(f"remote hash/finalize failed rc={status}")
    print(f"RAMSSH_CHUNKED_UPLOAD_OK bytes={len(payload)} sha256={expected} destination={args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
