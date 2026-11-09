#!/usr/bin/env python3
"""Stream the fixed /dev/omspiro read-only device over authenticated SSH."""
from __future__ import annotations

import argparse
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko  # noqa: E402


def load_private_key() -> paramiko.Ed25519Key:
    windows_key = Path.home() / ".ssh" / "id_ed25519"
    if windows_key.is_file():
        return paramiko.Ed25519Key.from_private_key_file(str(windows_key))
    text = subprocess.check_output(
        [
            "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e",
            "cat", "/home/user/openmitrastar-ramssh-keys/client_ed25519",
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return paramiko.Ed25519Key.from_private_key(io.StringIO(text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bytes", type=int, choices=(64, 0x1000000), required=True)
    args = parser.parse_args()
    command = (
        "/bin/busybox dd if=/dev/omspiro bs=64 count=1"
        if args.bytes == 64
        else "/bin/busybox cat /dev/omspiro"
    )
    output = args.output.resolve()
    temporary = output.with_name(output.name + ".part")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary.unlink(missing_ok=True)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    digest = hashlib.sha256()
    received = 0
    try:
        client.connect(
            args.host,
            username="root",
            pkey=load_private_key(),
            look_for_keys=False,
            allow_agent=False,
            timeout=5,
            banner_timeout=8,
            auth_timeout=8,
        )
        _, stdout, stderr = client.exec_command(command, timeout=300)
        with temporary.open("wb") as stream:
            while block := stdout.read(131072):
                stream.write(block)
                digest.update(block)
                received += len(block)
                if received > args.bytes:
                    raise RuntimeError(f"remote stream exceeded expected size {args.bytes}")
        err = stderr.read()
        status = stdout.channel.recv_exit_status()
        if status:
            raise RuntimeError(f"remote read rc={status} stderr={err!r}")
        if received != args.bytes:
            raise RuntimeError(f"received {received} bytes, expected {args.bytes}")
        temporary.replace(output)
        print(
            f"OMSPIRO_DOWNLOAD_PASS bytes={received} sha256={digest.hexdigest()} "
            f"output={output}"
        )
        return 0
    finally:
        client.close()
        if temporary.exists() and received != args.bytes:
            temporary.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
